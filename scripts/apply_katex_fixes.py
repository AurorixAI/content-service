import psycopg2, os, json

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# 1. G10_TB_§21_21_23_4
a1_fixed = (
    r'Преобразуем левую часть: '
    r'1) $\dfrac{\tg \alpha + \tg \beta}{\tg(\alpha + \beta)} = (\tg \alpha + \tg \beta) : \left( \dfrac{\tg \alpha + \tg \beta}{1 - \tg \alpha \tg \beta} \right) = 1 - \tg \alpha \tg \beta$. '
    r'2) $\dfrac{\tg \alpha - \tg \beta}{\tg(\alpha - \beta)} = (\tg \alpha - \tg \beta) : \left( \dfrac{\tg \alpha - \tg \beta}{1 + \tg \alpha \tg \beta} \right) = 1 + \tg \alpha \tg \beta$. '
    r'Складываем: $(1 - \tg \alpha \tg \beta) + (1 + \tg \alpha \tg \beta) + 2 \tg^{2} \alpha = 2 + 2 \tg^{2} \alpha = 2(1 + \tg^{2} \alpha) = \dfrac{2}{\cos^{2} \alpha}$. Тождество доказано.'
)
cur.execute('UPDATE tasks_master SET correct_answer_latex = %s WHERE id = %s', (a1_fixed, 'G10_TB_§21_21_23_4'))

# 2. G11_TB_25_1_3_8
cur.execute('SELECT distractor_meta FROM tasks_master WHERE id = %s', ('G11_TB_25_1_3_8',))
dm2 = cur.fetchone()[0]
d2_fixed = (
    r'Ученик при упрощении подынтегрального выражения записал $\sqrt{\dfrac{x}{x}}=\dfrac{x^{\dfrac{1}{2}}}{x}=x^{-\dfrac{1}{2}}$, '
    r'но при интегрировании перепутал формулу для степени $-\dfrac{1}{2}$ с формулой для степени $+\dfrac{1}{2}$ и получил первообразную $\dfrac{x^{\dfrac{1}{2}}}{\dfrac{1}{2}}=2\sqrt{x}$ '
    r'вместо правильной $\dfrac{x^{\dfrac{1}{2}}}{\dfrac{1}{2}}=2\sqrt{x}$ (тут формула верна), однако при подстановке пределов для первого слагаемого $\dfrac{x^{2}}{2}$ получил '
    r'$\left(\dfrac{16}{2} - \dfrac{1}{2}\right)=\dfrac{15}{2}$, а для второго слагаемого $2\sqrt{x}$ подставил пределы как $2 \cdot (4-1)=6$ вместо $2 \cdot (2-1)=2$, '
    r'и сложил $\dfrac{15}{2}+6=\dfrac{15}{2}+\dfrac{12}{2}=\dfrac{27}{2}$, но затем вычел лишнюю единицу и получил $\dfrac{21}{2}$.'
)
dm2[2]['error_logic_latex'] = d2_fixed
if 'explanation_latex' in dm2[2]:
    dm2[2]['explanation_latex'] = d2_fixed
cur.execute('UPDATE tasks_master SET distractor_meta = %s WHERE id = %s', (json.dumps(dm2), 'G11_TB_25_1_3_8'))

# 3. G11_TB_6_10*_6_94*
cur.execute('SELECT distractor_meta FROM tasks_master WHERE id = %s', ('G11_TB_6_10*_6_94*',))
dm3 = cur.fetchone()[0]
d3_fixed = r'Ученик использовал закон охлаждения Ньютона, но перепутал начальную и конечную температуры в формуле: $t=10 \cdot \dfrac{\ln\left(\dfrac{100}{30}\right)}{\ln\left(\dfrac{100}{60}\right)} \approx 40$ мин.'
dm3[1]['error_logic_latex'] = d3_fixed
if 'explanation_latex' in dm3[1]:
    dm3[1]['explanation_latex'] = d3_fixed
cur.execute('UPDATE tasks_master SET distractor_meta = %s WHERE id = %s', (json.dumps(dm3), 'G11_TB_6_10*_6_94*'))

# 4. G11_TB_?_11_а
cur.execute('SELECT distractor_meta FROM tasks_master WHERE id = %s', ('G11_TB_?_11_а',))
dm4 = cur.fetchone()[0]
d4_fixed = r'Ученик нашел $\tg(4x)$ по формуле двойного угла: $\tg(4x)=2 \cdot \dfrac{\dfrac{1}{4}}{1-\left(\dfrac{1}{4}\right)^{2}}=\dfrac{\dfrac{1}{2}}{\dfrac{15}{16}}=\dfrac{8}{15}$, и на этом остановился, приняв $\tg(4x)$ за $\tg(8x)$.'
dm4[1]['error_logic_latex'] = d4_fixed
if 'explanation_latex' in dm4[1]:
    dm4[1]['explanation_latex'] = d4_fixed
cur.execute('UPDATE tasks_master SET distractor_meta = %s WHERE id = %s', (json.dumps(dm4), 'G11_TB_?_11_а'))

# 5. G5_TB_11_414.1
q5_fixed = r'Вместо звёздочек поставьте пропущенные цифры: $\begin{array}{r}4 \ast 3 \cdot 2 \ast \\ \hline \ast 83 \\ + \quad \ast\ast\ast \\ \hline \ast\ast\ast\ast\ast\end{array}$'
cur.execute('UPDATE tasks_master SET question_latex = %s WHERE id = %s', (q5_fixed, 'G5_TB_11_414.1'))

# 6. G5_TB_29_1105
cur.execute('SELECT distractor_meta FROM tasks_master WHERE id = %s', ('G5_TB_29_1105',))
dm6 = cur.fetchone()[0]
d6_fixed = r'Ученик правильно вычел $500$ г из $2100$ г, получив $1600$ г. Однако он проигнорировал условие «в $3$ раза больше» и просто поровну разделил оставшуюся крупу между первой и второй банками ($\dfrac{1600}{2} = 800$ г).'
dm6[2]['error_logic_latex'] = d6_fixed
if 'explanation_latex' in dm6[2]:
    dm6[2]['explanation_latex'] = d6_fixed
cur.execute('UPDATE tasks_master SET distractor_meta = %s WHERE id = %s', (json.dumps(dm6), 'G5_TB_29_1105'))

conn.commit()
print('Successfully applied 6 exact KaTeX repairs to DB.')
