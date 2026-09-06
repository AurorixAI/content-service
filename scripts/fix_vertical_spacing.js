const fs = require('fs');

const filePath = '/Users/arslan/Desktop/ALGO/algo-front/src/app/admin/diagnostics/[id]/report/page.tsx';
let content = fs.readFileSync(filePath, 'utf8');

const journalBlock = `{/* ── TAB 1: Error Journal — paginated ──────────────────────────── */}
          {activeTab === "journal" && rj.error_patterns.length > 0 && (() => {
            const totalPages = Math.ceil(rj.error_patterns.length / ERRORS_PER_PAGE);
            const pageErrors = rj.error_patterns.slice(
              errorPage * ERRORS_PER_PAGE,
              (errorPage + 1) * ERRORS_PER_PAGE
            );
            return (
              <motion.div variants={fade} className="bg-white rounded-[28px] border border-slate-200/80 shadow-[0_18px_50px_-28px_rgba(15,23,42,0.32)] overflow-hidden">

                {/* ── Journal Header ── */}
                <div className="flex items-center gap-3 px-6 sm:px-8 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-slate-50/70">
                  <div className="flex items-center gap-2.5 flex-1 min-w-0">
                    <div className="w-10 h-10 rounded-2xl bg-rose-50 ring-1 ring-rose-100 flex items-center justify-center flex-shrink-0">
                      <FileText className="w-4 h-4 text-rose-500" />
                    </div>
                    <div>
                      <h2 className="font-bold text-slate-900 text-sm leading-none">Журнал ошибок</h2>
                    </div>
                  </div>
                  {/* Compact pagination in header */}
                  {totalPages > 1 && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button onClick={() => setErrorPage(p => Math.max(0, p - 1))} disabled={errorPage === 0}
                        className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>
                      </button>
                      {Array.from({ length: totalPages }).map((_, pi) => (
                        <button key={pi} onClick={() => setErrorPage(pi)}
                          className={\`w-7 h-7 rounded-lg text-xs font-bold transition-all \${
                            pi === errorPage ? "bg-slate-900 text-white" : "text-slate-400 hover:bg-slate-100"
                          }\`}>{pi + 1}</button>
                      ))}
                      <button onClick={() => setErrorPage(p => Math.min(totalPages - 1, p + 1))} disabled={errorPage === totalPages - 1}
                        className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" /></svg>
                      </button>
                    </div>
                  )}
                </div>

                {/* ── Error Entries ── */}
                <div className="divide-y divide-slate-100/80">
                  {pageErrors.map((err, i) => {
                    const globalIdx = errorPage * ERRORS_PER_PAGE + i + 1;
                    const isDistractor = err.eval_category === "distractor";
                    const hasMcqOptions = err.answer_options && err.answer_options.length > 0;

                    return (
                      <div key={i} className="px-6 sm:px-8 py-6 sm:py-7 space-y-5 sm:space-y-6 hover:bg-slate-50/30 transition-colors">

                        {/* ── Entry Top Bar: number pill + skill name ── */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="px-2.5 py-0.5 rounded-md text-[11px] font-black tracking-wider bg-slate-900 text-white shadow-2xs">
                            № {globalIdx}
                          </span>
                          {err.skill_name_ru && (
                            <span className="text-xs font-semibold text-slate-500 truncate">
                              {err.skill_name_ru}
                            </span>
                          )}
                        </div>

                        {/* ── Task Question Container ── */}
                        <div className="rounded-2xl bg-slate-50/70 border border-slate-200/80 p-4.5 sm:p-5 shadow-2xs">
                          <div className="mb-2.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                            Условие задачи
                          </div>
                          <MathRenderer
                            text={pickTaskDisplayText({
                              question_text: err.question_text || "",
                              question_latex: err.question_latex || null,
                            }) || err.skill_name_ru}
                            block
                            className="text-[14px] sm:text-[14.5px] text-slate-800 leading-relaxed font-medium whitespace-pre-wrap break-words"
                          />
                        </div>

                          {/* MCQ Options (if applicable) */}
                          {hasMcqOptions && (() => {
                            const optionsList = err.answer_options || [];
                            const optionsLatex = err.answer_options_latex || [];

                            // Deduplicate options list by canonical key to guarantee no duplicate options (e.g. A and E) are rendered
                            const seenKeys = new Set<string>();
                            const uniqueOptions: { opt: string; latex: string; originalIndex: number }[] = [];
                            optionsList.forEach((opt, oi) => {
                              const key = canonicalAnswerKey(opt) || (opt || "").trim().toLowerCase();
                              if (key && !seenKeys.has(key)) {
                                seenKeys.add(key);
                                uniqueOptions.push({ opt, latex: optionsLatex[oi] || opt, originalIndex: oi });
                              }
                            });

                            const hasLongOptions = uniqueOptions.some(item => (item.opt || "").length > 60);
                            const hasMatchedStudentOpt = uniqueOptions.some((item, oi) => matchesOption(err.student_answer, item.opt, item.latex, oi));

                            return (
                              <div className="space-y-3">
                                <div className={\`grid gap-3 sm:gap-3.5 \${hasLongOptions ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"}\`}>
                                  {uniqueOptions.map((item, oi) => {
                                    const isCorrect = matchesOption(err.correct_answer, item.opt, item.latex, oi);
                                    const isStudentAnswer = matchesOption(err.student_answer, item.opt, item.latex, oi);
                                    return (
                                      <div key={oi} className={\`flex items-center gap-3 p-3.5 sm:p-4 rounded-xl border transition-all \${
                                        isCorrect
                                          ? "bg-emerald-50/70 border-emerald-200/90 shadow-2xs"
                                          : isStudentAnswer && !isCorrect
                                            ? "bg-white border-rose-200/90 shadow-2xs"
                                            : "bg-white border-slate-200/70 hover:border-slate-300"
                                      }\`}>
                                        <span className={\`w-6.5 h-6.5 rounded-lg text-[11px] font-black flex items-center justify-center flex-shrink-0 \${
                                          isCorrect ? "bg-emerald-600 text-white" :
                                          isStudentAnswer ? "bg-rose-500 text-white" :
                                          "bg-slate-100 text-slate-500"
                                        }\`}>{String.fromCharCode(65 + oi)}</span>
                                        <div className="flex-1 min-w-0">
                                          <MathRenderer
                                            text={item.latex}
                                            className={\`text-[13.5px] sm:text-[14px] leading-snug break-words \${
                                              isCorrect ? "font-medium text-emerald-950" :
                                              isStudentAnswer && !isCorrect ? "font-medium text-rose-950" :
                                              "font-normal text-slate-700"
                                            }\`}
                                          />
                                        </div>
                                        {isCorrect && <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />}
                                        {isStudentAnswer && !isCorrect && <XCircle className="w-4 h-4 text-rose-500 flex-shrink-0" />}
                                      </div>
                                    );
                                  })}
                                </div>
                                {!hasMatchedStudentOpt && err.student_answer && !["idk", "__wrong__", "test"].includes(err.student_answer.trim().toLowerCase()) && (
                                  <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-rose-50/70 border border-rose-200/80 text-xs font-medium text-rose-950">
                                    <XCircle className="w-3.5 h-3.5 text-rose-500 flex-shrink-0" />
                                    <span className="font-semibold text-rose-700">Введённый ответ ученика:</span>
                                    <MathRenderer text={err.student_answer_latex || err.student_answer} className="font-medium text-[13.5px]" />
                                  </div>
                                )}
                              </div>
                            );
                          })()}

                          {/* Text answer comparison (non-MCQ) */}
                          {!hasMcqOptions && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 sm:gap-4">
                              {/* Student answer */}
                              <div className="rounded-xl border bg-white border-rose-200/90 p-4 shadow-2xs">
                                <div className="flex items-center gap-1.5 mb-2">
                                  <XCircle className="w-3.5 h-3.5 text-rose-400" />
                                  <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Ответ ученика</span>
                                </div>
                                {err.student_answer
                                  ? <MathRenderer text={err.student_answer_latex || err.student_answer} block className="text-[13.5px] sm:text-[14px] font-medium text-rose-950 leading-relaxed break-words" />
                                  : <span className="text-xs font-semibold text-slate-400">—</span>
                                }
                              </div>
                              {/* Correct answer */}
                              <div className="rounded-xl border bg-emerald-50/70 border-emerald-200/90 p-4 shadow-2xs">
                                <div className="flex items-center gap-1.5 mb-2">
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                                  <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Верный ответ</span>
                                </div>
                                {(err.correct_answer_latex || err.correct_answer)
                                  ? <MathRenderer text={err.correct_answer_latex || err.correct_answer || ""} block className="text-[13.5px] sm:text-[14px] font-medium text-emerald-950 leading-relaxed break-words" />
                                  : <span className="text-xs font-semibold text-slate-400">—</span>
                                }
                              </div>
                            </div>
                          )}

                          {/* Distractor explanation (real from DB) */}
                          {isDistractor && err.distractor_explanation && (
                            <div className="rounded-2xl bg-indigo-50/40 border border-indigo-100/90 p-4.5 sm:p-5 shadow-2xs relative">
                              <div className="mb-2.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-500/90">
                                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                                Анализ ошибки
                              </div>
                              <div className="text-[13.5px] sm:text-[14px] text-slate-700 leading-relaxed font-normal">
                                <MathRenderer text={err.distractor_explanation_latex || err.distractor_explanation} className="text-[13.5px] sm:text-[14px] text-slate-700 leading-relaxed" />
                              </div>
                            </div>
                          )}

                          {/* Generic distractor notice (no explanation available) */}
                          {isDistractor && !err.distractor_explanation && (
                            <div className="rounded-2xl bg-indigo-50/30 border border-indigo-100/80 p-4 shadow-2xs">
                              <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-500/90">
                                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                                Анализ ошибки
                              </div>
                              <p className="text-xs font-medium text-slate-600">Ученик выбрал характерный ложный вариант ответа (дистрактор).</p>
                            </div>
                          )}

                      </div>
                    );
                  })}
                </div>

                {/* ── Journal Footer ── */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-6 py-3 border-t border-slate-100 bg-slate-50/50">
                    <span className="text-xs text-slate-400">
                      Записи <span className="font-semibold text-slate-700">{errorPage * ERRORS_PER_PAGE + 1}–{Math.min((errorPage + 1) * ERRORS_PER_PAGE, rj.error_patterns.length)}</span> из <span className="font-semibold text-slate-700">{rj.error_patterns.length}</span>
                    </span>
                    <div className="flex gap-2">
                      <button onClick={() => setErrorPage(p => Math.max(0, p - 1))} disabled={errorPage === 0}
                        className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                        ← Назад
                      </button>
                      <button onClick={() => setErrorPage(p => Math.min(totalPages - 1, p + 1))} disabled={errorPage === totalPages - 1}
                        className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                        Вперёд →
                      </button>
                    </div>
                  </div>
                )}
              </motion.div>
            );
          })()}`;

const startIdx = content.indexOf('{/* ── TAB 1: Error Journal');
const endIdx = content.indexOf('{/* ── TAB 2: Skills & Gaps Breakdown');

if (startIdx !== -1 && endIdx !== -1) {
  content = content.substring(0, startIdx) + journalBlock + "\n\n          " + content.substring(endIdx);
  fs.writeFileSync(filePath, content, 'utf8');
  console.log("Successfully fixed vertical spacing in page.tsx!");
} else {
  console.error("Could not find startIdx or endIdx!");
  process.exit(1);
}
