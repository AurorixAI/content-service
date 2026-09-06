const psycopg2 = require('pg');
const { Client } = psycopg2;

const client = new Client({
  user: 'algo',
  password: 'algo_password',
  host: '127.0.0.1',
  port: 5433,
  database: 'algo_diagnostic'
});

async function main() {
  await client.connect();
  const res = await client.query("SELECT id, report_json FROM diag_reports WHERE report_json::text LIKE '%G10_TB_1_8_3%';");
  for (const row of res.rows) {
    const rj = typeof row.report_json === 'string' ? JSON.parse(row.report_json) : row.report_json;
    for (const ep of rj.error_patterns || []) {
      if (ep.task_id === 'G10_TB_1_8_3') {
        console.log('--- FOUND REPORT', row.id, '---');
        console.log('student_answer:', JSON.stringify(ep.student_answer));
        console.log('answer_options:', JSON.stringify(ep.answer_options));
        console.log('answer_options_latex:', JSON.stringify(ep.answer_options_latex));
      }
    }
  }
  await client.end();
}

main().catch(console.error);
