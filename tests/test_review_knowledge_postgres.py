"""New taxonomy and bank writes/rollback share a real PostgreSQL transaction."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text
from test_guarded_content_repair_postgres import pg
from tools.content_review.build_n01_manifest import choices,d
from tools.content_review.guarded_repair import apply,rollback,candidate,fingerprint,_load
from tools.content_review.n01_review_knowledge import node


def _cleanup(pg):
    with pg.begin() as conn:
        conn.execute(text("DELETE FROM tasks_master WHERE id='REVIEW_TASK'"))
        for node_id in ('REVIEW_LEAF', 'REVIEW_OLD', 'REVIEW_PARENT'):
            conn.execute(text("DELETE FROM knowledge_hierarchy WHERE id=:id"), {'id': node_id})


@pytest.fixture
def review(pg):
    # Fixture must satisfy both the live schema and `alembic upgrade head`, where
    # tasks need an existing L4 skill (trigger) and explicit NOT NULL columns.
    _cleanup(pg)
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru) VALUES ('REVIEW_PARENT','L3','Parent')"))
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,parent_id,name_ru) VALUES ('REVIEW_OLD','L4','REVIEW_PARENT','Old skill')"))
        conn.execute(text("""INSERT INTO tasks_master(id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load,is_active,tags)
                             VALUES ('REVIEW_TASK','REVIEW_OLD','Old','0','exact_number','B','apply',true,'{}')"""))
        row=_load(conn,['REVIEW_TASK'],False)[0]
    changes=choices('New','$1$',[d('$2$','Incorrect','wrong'),d('$3$','Incorrect','wrong'),d('$4$','Incorrect','wrong')],skill_id='REVIEW_LEAF')
    entry={'id':'REVIEW_TASK','before_sha256':fingerprint(row),'changes':changes,'reason':'Reviewed','evidence':'Independent math'}
    entry['after_sha256']=fingerprint(candidate(row,entry,'review-test'))
    manifest={'batch':'review-test','repairs':[entry], 'knowledge_nodes':[node('REVIEW_LEAF','L4','REVIEW_PARENT','Reviewed skill','Atomic ability',10,1)]}
    yield pg,manifest,row
    _cleanup(pg)


def test_taxonomy_dry_run_apply_repeat_exact_rollback(review,tmp_path):
    engine,manifest,before=review;backup=tmp_path/'backup.json'
    assert apply(engine,manifest)['knowledge_added']==['REVIEW_LEAF']
    with engine.connect() as conn:assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'"))==0
    assert len(apply(engine,manifest,execute=True,backup=backup)['updated'])==1
    assert apply(engine,manifest,execute=True,backup=tmp_path/'repeat.json')['already_applied']==['REVIEW_TASK']
    assert not (tmp_path/'repeat.json').exists()
    rollback(engine,json.loads(backup.read_text()),execute=True)
    with engine.connect() as conn:
        assert fingerprint(_load(conn,['REVIEW_TASK'],False)[0])==fingerprint(before)
        assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'"))==0


@pytest.mark.parametrize('bad',['active','wrong_parent','cycle','duplicate','undefined_ability'])
def test_invalid_taxonomy_refuses_every_write(review,tmp_path,bad):
    engine,manifest,before=review;manifest=copy.deepcopy(manifest);n=manifest['knowledge_nodes'][0]
    if bad=='active':n['is_active']=True
    elif bad=='wrong_parent':n['parent_id']='missing'
    elif bad=='cycle':n['parent_id']=n['id']
    elif bad=='duplicate':manifest['knowledge_nodes'].append(dict(n))
    else:n['assessed_ability']=None
    with pytest.raises(ValueError):apply(engine,manifest,execute=True,backup=tmp_path/'bad.json')
    with engine.connect() as conn:
        assert fingerprint(_load(conn,['REVIEW_TASK'],False)[0])==fingerprint(before)
        assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'"))==0
    assert not (tmp_path/'bad.json').exists()


def test_existing_node_is_never_repurposed_and_new_review_blocks_rollback(review,tmp_path):
    engine,manifest,_=review;backup=tmp_path/'backup.json'
    apply(engine,manifest,execute=True,backup=backup)
    with engine.begin() as conn:conn.execute(text("UPDATE knowledge_hierarchy SET name_ru='Newer reviewed definition' WHERE id='REVIEW_LEAF'"))
    with pytest.raises(ValueError,match='drift'):apply(engine,manifest)
    with pytest.raises(ValueError,match='drift'):rollback(engine,json.loads(backup.read_text()),execute=True)
    with engine.connect() as conn:assert _load(conn,['REVIEW_TASK'],False)[0]['correct_answer']=='$1$'


def test_two_workers_insert_one_node_and_one_bank_change(review,tmp_path):
    engine,manifest,_=review
    def run(i):return apply(engine,manifest,execute=True,backup=tmp_path/f'worker-{i}.json')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(len(r['updated']) for r in results)==[0,1]
    assert len(list(tmp_path.glob('worker-*.json')))==1


def test_protected_repairs_need_explicit_ack_and_write_nothing(review,tmp_path):
    engine,manifest,before=review;manifest=copy.deepcopy(manifest);manifest['historical_protection_required']=['REVIEW_TASK']
    for execute in (False,True):
        with pytest.raises(ValueError,match='historical pupil answers'):apply(engine,manifest,execute=execute,backup=tmp_path/'p.json')
    assert not (tmp_path/'p.json').exists()
    with engine.connect() as conn:
        assert fingerprint(_load(conn,['REVIEW_TASK'],False)[0])==fingerprint(before)
        assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'"))==0
    assert len(apply(engine,manifest,execute=True,backup=tmp_path/'p.json',ack_protected=True)['updated'])==1
