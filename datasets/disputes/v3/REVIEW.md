# Label review: v3, borderline cases

Ruling column: run `eval-studionet-1792681664.json` (policy `policies/fbp-v5.json`, contract `0x23069f4C16F21E48d0E74e6E358485f1FE66B45f`). Mark **Your call** as ✅ (label right), ❌ (label wrong, say what it should be) or ? (unsure). Disagreements between label and ruling are marked ⚠️.

## loop_tail_short (20)

| Case | Request | Output | Tokens out / reasoning | Label | Ruling | Your call |
|---|---|---|---|---|---|---|
| `author-looptail-short` | Who wrote 'Pride and Prejudice'? | Jane Austen wrote 'Pride and Prejudice', published in 1813. ⏎ Jane Austen wrote 'Pride. Jane Austen wrote 'Pride. Jane Austen wrote 'Pride. | 35 / 0 | none 0%–25% | degenerate 25% | |
| `bash-looptail-short` | Write a bash one-liner that counts the lines in all .py files in the current directory tree. | find . -name '*.py' -print0 \| xargs -0 cat \| wc -l ⏎ find . -name '*.py'. find . -name '*.py'. find . -name '*.py'. | 29 / 0 | none 0%–25% | degenerate 25% | |
| `berlin-looptail-short` | What year did the Berlin Wall fall? | The Berlin Wall fell in 1989, on 9 November. ⏎ The Berlin Wall fell. The Berlin Wall fell. The Berlin Wall fell. | 28 / 0 | none 0%–25% | degenerate 25% | |
| `cafe-looptail-short` | Suggest a name for a coffee shop run by two retired astronomers, with a one-line rationale. | Event Horizon Espresso: once you step in, you won't want to leave. ⏎ Event Horizon Espresso: once. Event Horizon Espresso: once. Event Horizon Espresso: once. | 39 / 0 | none 0%–25% | degenerate 25% | |
| `capital-looptail-short` | What is the capital of Australia? One sentence. | The capital of Australia is Canberra. ⏎ The capital of Australia. The capital of Australia. The capital of Australia. | 29 / 0 | none 0%–25% | degenerate 25% | |
| `email-looptail-short` | Draft a polite email declining a meeting on Thursday and proposing Friday morning instead. | Hi Sam, ⏎  ⏎ Thank you for the invite. Unfortunately I can't make Thursday. Would Friday morning work for you instead? I'm free from 9 to 12. ⏎  ⏎ Best regards, ⏎ Alex ⏎ Hi Sam, Thank you. Hi Sam, Thank you. Hi Sam, Tha… | 54 / 0 | none 0%–25% | degenerate 25% | |
| `equation-looptail-short` | Solve for x: 3x + 7 = 22. Show the steps. | 3x + 7 = 22 ⏎ 3x = 15 ⏎ x = 5 ⏎ 3x + 7 =. 3x + 7 =. 3x + 7 =. | 14 / 0 | none 0%–25% | degenerate 25% | |
| `fahrenheit-looptail-short` | Convert 72 degrees Fahrenheit to Celsius. Show the formula. | C = (F - 32) x 5/9 = (72 - 32) x 5/9 = 22.2 degrees Celsius. ⏎ C = (F -. C = (F -. C = (F -. | 23 / 0 | none 0%–25% | degenerate 25% | |
| `haiku-looptail-short` | Write a haiku about rain. | Soft rain on the roof ⏎ the gutters hum their one note ⏎ streets turn into sky ⏎ Soft rain on the. Soft rain on the. Soft rain on the. | 32 / 0 | none 0%–25% | degenerate 25% | |
| `hash-looptail-short` | Explain what a hash function is to a 12-year-old in 3 sentences. | A hash function is like a machine that turns any message into a short code. The same message always gives the same code, but even a tiny change gives a totally different one. Computers use these codes to check that file… | 76 / 0 | none 0%–25% | degenerate 25% | |
| `headphones-looptail-short` | Write a two-line product description for noise-cancelling headphones. | Shut out the commute and turn up the detail. ⏎ All-day comfort, 30-hour battery, silence on demand. ⏎ Shut out the commute. Shut out the commute. Shut out the commute. | 41 / 0 | none 0%–25% | degenerate 25% | |
| `json-looptail-short` | Give a JSON object with keys name, age and city for a fictional person. | {"name": "Maya Lind", "age": 34, "city": "Lisbon"} ⏎ {"name": "Maya Lind", "age":. {"name": "Maya Lind", "age":. {"name": "Maya Lind", "age":. | 35 / 0 | none 0%–25% | degenerate 25% | |
| `multiply-looptail-short` | What is 17 x 23? | 17 x 23 = 391. ⏎ 17 x 23 =. 17 x 23 =. 17 x 23 =. | 12 / 0 | none 0%–25% | degenerate 25% | |
| `palindrome-looptail-short` | Write a Python function that returns True if a string is a palindrome, ignoring case. | def is_palindrome(s: str) -> bool: ⏎     s = s.lower() ⏎     return s == s[::-1] ⏎ def is_palindrome(s: str) ->. def is_palindrome(s: str) ->. def is_palindrome(s: str) ->. | 42 / 0 | none 0%–25% | degenerate 25% | |
| `sql-looptail-short` | Write a SQL query that returns the 5 customers with the highest total order amount, from tables customers(id, name) and… | SELECT c.name, SUM(o.amount) AS total ⏎ FROM customers c ⏎ JOIN orders o ON o.customer_id = c.id ⏎ GROUP BY c.id, c.name ⏎ ORDER BY total DESC ⏎ LIMIT 5; ⏎ SELECT c.name, SUM(o.amount) AS. SELECT c.name, SUM(o.amount) A… | 61 / 0 | none 0%–25% | degenerate 25% | |
| `summary-looptail-short` | Summarise in two sentences: Photosynthesis is the process by which green plants use sunlight, water and carbon dioxide … | Plants use sunlight, water and carbon dioxide to make glucose through photosynthesis. It happens mostly in leaf chloroplasts and releases oxygen. ⏎ Plants use sunlight, water. Plants use sunlight, water. Plants use sunl… | 58 / 0 | none 0%–25% | degenerate 25% | |
| `tcpudp-looptail-short` | Explain the difference between TCP and UDP in under 80 words. | TCP sets up a connection and guarantees delivery, order and error checking, so it suits web pages and file transfers. UDP sends packets without a connection or delivery guarantees, which makes it faster and lighter, so … | 77 / 0 | none 0%–25% | degenerate 25% | |
| `testing-looptail-short` | List three benefits of unit testing. | 1. Catches bugs early, when they are cheap to fix. ⏎ 2. Makes refactoring safer. ⏎ 3. Documents how the code is meant to behave. ⏎ 1. Catches bugs early,. 1. Catches bugs early,. 1. Catches bugs early,. | 49 / 0 | none 0%–25% | degenerate 25% | |
| `translate-looptail-short` | Translate to French: 'The meeting has been moved to next Tuesday.' | La reunion a ete deplacee a mardi prochain. ⏎ La reunion a ete. La reunion a ete. La reunion a ete. | 25 / 0 | none 0%–25% | degenerate 25% | |
| `zip-looptail-short` | Give me a regex that matches US ZIP codes (5 digits, with an optional -4 digit extension). | ^\d{5}(-\d{4})?$ ⏎ ^\d{5}(-\d{4})?$. ^\d{5}(-\d{4})?$. ^\d{5}(-\d{4})?$. | 18 / 0 | none 0%–25% | none 0% | |

## max_tokens_truncation (10)

| Case | Request | Output | Tokens out / reasoning | Label | Ruling | Your call |
|---|---|---|---|---|---|---|
| `bash-truncated` | Write a bash one-liner that counts the lines in all .py files in the current directory tree. | find . -name '*.py' -print0 \| xar | 9 / 0 | none 0%–25% | none 0% | |
| `cafe-truncated` | Suggest a name for a coffee shop run by two retired astronomers, with a one-line rationale. | Event Horizon Espresso: once you step in, yo | 11 / 0 | none 0%–25% | none 0% | |
| `haiku-truncated` | Write a haiku about rain. | Soft rain on the roof ⏎ the gutters hum their one n | 13 / 0 | none 0%–25% | none 0% | |
| `headphones-truncated` | Write a two-line product description for noise-cancelling headphones. | Shut out the commute and turn up the detail. ⏎ All-day comfort, 30 | 16 / 0 | none 0%–25% | none 0% | |
| `json-truncated` | Give a JSON object with keys name, age and city for a fictional person. | {"name": "Maya Lind", "age": 34,  | 9 / 0 | none 0%–25% | none 0% | |
| `multiply-truncated` | What is 17 x 23? | 17 x 23 = | 3 / 0 | none 0%–25% | none 0% | |
| `palindrome-truncated` | Write a Python function that returns True if a string is a palindrome, ignoring case. | def is_palindrome(s: str) -> bool: ⏎     s = s.lower | 13 / 0 | none 0%–25% | none 0% | |
| `sql-truncated` | Write a SQL query that returns the 5 customers with the highest total order amount, from tables customers(id, name) and… | SELECT c.name, SUM(o.amount) AS total ⏎ FROM customers c ⏎ JOIN orders o ON o.customer_id = c.id ⏎ GR | 24 / 0 | none 0%–25% | none 0% | |
| `translate-truncated` | Translate to French: 'The meeting has been moved to next Tuesday.' | La reunion a ete deplacee a  | 7 / 0 | none 0%–25% | none 0% | |
| `zip-truncated` | Give me a regex that matches US ZIP codes (5 digits, with an optional -4 digit extension). | ^\d{5}(-\d | 3 / 0 | none 0%–25% | none 0% | |

## wrong_but_attempted (20)

| Case | Request | Output | Tokens out / reasoning | Label | Ruling | Your call |
|---|---|---|---|---|---|---|
| `author-wrong` | Who wrote 'Pride and Prejudice'? | Charlotte Bronte wrote 'Pride and Prejudice', published in 1847. | 16 / 0 | none 0%–0% | none 0% | |
| `bash-wrong` | Write a bash one-liner that counts the lines in all .py files in the current directory tree. | wc -l *.py | 3 / 0 | none 0%–0% | none 0% | |
| `berlin-wrong` | What year did the Berlin Wall fall? | The Berlin Wall fell in 1991. | 8 / 0 | none 0%–0% | none 0% | |
| `cafe-wrong` | Suggest a name for a coffee shop run by two retired astronomers, with a one-line rationale. | Coffee Place: it is a place for coffee. | 10 / 0 | none 0%–0% | none 0% | |
| `capital-wrong` | What is the capital of Australia? One sentence. | The capital of Australia is Sydney. | 9 / 0 | none 0%–0% | none 0% | |
| `email-wrong` | Draft a polite email declining a meeting on Thursday and proposing Friday morning instead. | Can't do Thursday. Friday. | 7 / 0 | none 0%–0% | none 0% | |
| `equation-wrong` | Solve for x: 3x + 7 = 22. Show the steps. | 3x + 7 = 22 ⏎ 3x = 12 ⏎ x = 4 | 7 / 0 | none 0%–0% | none 0% | |
| `fahrenheit-wrong` | Convert 72 degrees Fahrenheit to Celsius. Show the formula. | C = (F - 32) x 9/5 = (72 - 32) x 9/5 = 72 degrees Celsius. | 15 / 0 | none 0%–0% | none 0% | |
| `haiku-wrong` | Write a haiku about rain. | Rain is falling down ⏎ it is wet ⏎ I like it | 10 / 0 | none 0%–0% | none 0% | |
| `hash-wrong` | Explain what a hash function is to a 12-year-old in 3 sentences. | A hash function is a way to lock a message with a password. You can unlock it later with the same password to read the message again. Computers use it to hide secrets. | 42 / 0 | none 0%–0% | none 0% | |
| `headphones-wrong` | Write a two-line product description for noise-cancelling headphones. | These are headphones. ⏎ They cancel noise. | 10 / 0 | none 0%–0% | none 0% | |
| `json-wrong` | Give a JSON object with keys name, age and city for a fictional person. | {"name": "Maya Lind", "age": 34, city: "Lisbon"} | 12 / 0 | none 0%–0% | none 0% | |
| `multiply-wrong` | What is 17 x 23? | 17 x 23 = 381. | 4 / 0 | none 0%–0% | none 0% | |
| `palindrome-wrong` | Write a Python function that returns True if a string is a palindrome, ignoring case. | def is_palindrome(s: str) -> bool: ⏎     return s == s[::-1] | 15 / 0 | none 0%–0% | none 0% | |
| `sql-wrong` | Write a SQL query that returns the 5 customers with the highest total order amount, from tables customers(id, name) and… | SELECT c.name, o.amount ⏎ FROM customers c ⏎ JOIN orders o ON o.customer_id = c.id ⏎ ORDER BY o.amount DESC ⏎ LIMIT 5; | 28 / 0 | none 0%–0% | none 0% | |
| `summary-wrong` | Summarise in two sentences: Photosynthesis is the process by which green plants use sunlight, water and carbon dioxide … | Plants use sunlight and oxygen to make glucose through photosynthesis. It happens in the roots and releases carbon dioxide. | 31 / 0 | none 0%–0% | none 0% | |
| `tcpudp-wrong` | Explain the difference between TCP and UDP in under 80 words. | UDP sets up a connection and guarantees delivery and order. TCP sends packets without guarantees, which makes it faster, so it suits live video and games. | 39 / 0 | none 0%–0% | none 0% | |
| `testing-wrong` | List three benefits of unit testing. | 1. Makes the code run faster. ⏎ 2. Reduces the size of the binary. ⏎ 3. Catches some bugs. | 22 / 0 | none 0%–0% | none 0% | |
| `translate-wrong` | Translate to French: 'The meeting has been moved to next Tuesday.' | La reunion a ete annulee mardi prochain. | 10 / 0 | none 0%–0% | none 0% | |
| `zip-wrong` | Give me a regex that matches US ZIP codes (5 digits, with an optional -4 digit extension). | ^\d{5}$  (this matches all US ZIP codes) | 10 / 0 | none 0%–0% | none 0% | |

## reasoning_below_threshold (4)

| Case | Request | Output | Tokens out / reasoning | Label | Ruling | Your call |
|---|---|---|---|---|---|---|
| `bash-reasoning-ok` | Write a bash one-liner that counts the lines in all .py files in the current directory tree. | find . -name '*.py' -print0 \| xargs -0 cat \| wc -l | 13 / 3000 | none 0%–0% | none 0% | |
| `equation-reasoning-ok` | Solve for x: 3x + 7 = 22. Show the steps. | 3x + 7 = 22 ⏎ 3x = 15 ⏎ x = 5 | 7 / 3000 | none 0%–0% | none 0% | |
| `palindrome-reasoning-ok` | Write a Python function that returns True if a string is a palindrome, ignoring case. | def is_palindrome(s: str) -> bool: ⏎     s = s.lower() ⏎     return s == s[::-1] | 19 / 3000 | none 0%–0% | none 0% | |
| `sql-reasoning-ok` | Write a SQL query that returns the 5 customers with the highest total order amount, from tables customers(id, name) and… | SELECT c.name, SUM(o.amount) AS total ⏎ FROM customers c ⏎ JOIN orders o ON o.customer_id = c.id ⏎ GROUP BY c.id, c.name ⏎ ORDER BY total DESC ⏎ LIMIT 5; | 36 / 3000 | none 0%–0% | none 0% | |

## wrong_language (10)

| Case | Request | Output | Tokens out / reasoning | Label | Ruling | Your call |
|---|---|---|---|---|---|---|
| `author-spanish` | Who wrote 'Pride and Prejudice'? | Jane Austen escribio 'Orgullo y prejuicio', publicada en 1813. | 16 / 0 | degenerate 50%–100% | degenerate 100% | |
| `berlin-spanish` | What year did the Berlin Wall fall? | El Muro de Berlin cayo en 1989, el 9 de noviembre. | 13 / 0 | degenerate 50%–100% | degenerate 100% | |
| `capital-spanish` | What is the capital of Australia? One sentence. | La capital de Australia es Canberra. | 9 / 0 | degenerate 50%–100% | degenerate 100% | |
| `email-spanish` | Draft a polite email declining a meeting on Thursday and proposing Friday morning instead. | Hola Sam, ⏎  ⏎ Gracias por la invitacion. Lamentablemente no puedo el jueves. Te iria bien el viernes por la manana? Estoy libre de 9 a 12. ⏎  ⏎ Saludos, ⏎ Alex | 38 / 0 | degenerate 50%–100% | degenerate 100% | |
| `equation-spanish` | Solve for x: 3x + 7 = 22. Show the steps. | 3x + 7 = 22 ⏎ 3x = 15 ⏎ x = 5 (la solucion es cinco) | 12 / 0 | none 0%–25% | degenerate 25% | |
| `fahrenheit-spanish` | Convert 72 degrees Fahrenheit to Celsius. Show the formula. | C = (F - 32) x 5/9 = (72 - 32) x 5/9 = 22,2 grados Celsius. | 15 / 0 | none 0%–25% | none 0% | |
| `hash-spanish` | Explain what a hash function is to a 12-year-old in 3 sentences. | Una funcion hash es como una maquina que convierte cualquier mensaje en un codigo corto. El mismo mensaje siempre da el mismo codigo, pero un pequeno cambio da uno totalmente distinto. Los ordenadores usan estos codigos… | 67 / 0 | degenerate 50%–100% | degenerate 100% | |
| `summary-spanish` | Summarise in two sentences: Photosynthesis is the process by which green plants use sunlight, water and carbon dioxide … | Las plantas usan luz solar, agua y dioxido de carbono para producir glucosa mediante la fotosintesis. Ocurre sobre todo en los cloroplastos de las hojas y libera oxigeno. | 43 / 0 | degenerate 50%–100% | degenerate 100% | |
| `tcpudp-spanish` | Explain the difference between TCP and UDP in under 80 words. | TCP establece una conexion y garantiza la entrega, el orden y la comprobacion de errores. UDP envia paquetes sin conexion ni garantias, por lo que es mas rapido y sirve para video en directo y juegos. | 50 / 0 | degenerate 50%–100% | degenerate 100% | |
| `testing-spanish` | List three benefits of unit testing. | 1. Detecta errores pronto, cuando son baratos de arreglar. ⏎ 2. Hace la refactorizacion mas segura. ⏎ 3. Documenta como debe comportarse el codigo. | 36 / 0 | degenerate 50%–100% | degenerate 100% | |

