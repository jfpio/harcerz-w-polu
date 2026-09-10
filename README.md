# Harcerz w polu

Cyfrowa, przeszukiwalna transkrypcja książki Zygmunta Wyrobka **„Harcerz w polu. Zabawy i gry terenowe”**, wydanie piąte, Kraków 1946.

Strona jest przygotowana do publikacji pod adresem:

<https://jfpio.github.io/harcerz-w-polu/>

## Źródło

Skan pobrano z [Polony / Biblioteki Narodowej](https://polona.pl/item-view/0782bd3a-4d20-41be-86f8-bcdfc65555c5?page=0). Rekord Polony oznacza obiekt jako **„Domena publiczna”**.

Repozytorium zachowuje oryginalny PDF oraz trzy warstwy wydania cyfrowego:

1. odpowiedzi Mistral OCR 4.1 w `data/ocr/chunks/`,
2. redakcyjne pliki Markdown w `src/content/docs/`,
3. statyczną stronę Astro Starlight generowaną do `dist/`.

Transkrypcja zachowuje pisownię wydania z 1946 roku. Ma status publicznej wersji beta: poprawiane są błędy OCR, ale tekst nie jest modernizowany.

## Użycie z modelami językowymi

Możesz skorzystać z [gema „Harcerz w polu” w Google Gemini](https://gemini.google.com/gem/1hREsNgnceaNB66RNaOOoq9UqKBnK02JD?usp=sharing).

> **Asystent AI ma się skupiać na pomocy w wyszukaniu odpowiednich gier, eksploracji oraz do zadawania pytań, których często zapominamy przy projektowaniu gier. Pamiętaj jednak, że odpowiedzialność wychowawcza i dobieranie form do obranych przez Ciebie celów spoczywają jedynie na Twoich barkach.**

Prompt użyty w gemie:

```text
Masz pomóc użytkownikowi w dobieraniu i tworzeniu gier dla jego jednostki.
Kluczowe jest wpierw znalezienie odpowiednich gier, dopasowanych do jego potrzeb.
Następnie dostosowanie do jego konkretnej sytuacji, oraz zbalansowanie jej (liczba osób, wielkość obszaru, czas).

Odnoś się do konkretnych gier. Cytuj konkretne tytuły. NIE MOŻESZ ICH ZMYŚLAĆ/MODYFIKOWAĆ. Chodzi o to, by użytkownik mógł sam sprawdzić w książce całą treść.

Możesz pozwalać sobie na kreatywność, ale zaznacz to wtedy "Moja propozycja to...".

Możesz na sam koniec zaproponować symulację gry i przedyskutowanie 3 scenariuszy. Spróbuj wtedy znaleźć potencjalne dziury (exploits), które uczestnicy mogą wykorzystać. Zapytaj się użytkownika, czy zna sposób, by temu przeciwdziałać. Nie dawaj potencjalnych rozwiązań jako pierwszy.
Zadaj sobie i użytkownikowi pytania:
- Co może się zdarzyć, że gra zakończy się całkowitą dominacją jednej strony zbyt wcześnie?
- Czy może się zdarzyć sytuacja, że gra zakończy się za szybko? Np. przed połową planowanego czasu?
- Czy uczestnicy mogą oszukiwać, robić coś, co nie jest przewidziane regułami, co nie jest oczywiste? Dążymy do małej liczby reguł, ale musimy pamiętać, że gracze są kreatywni i że to, co nie jest zakazane, jest dozwolone. Szkoda by było, gdyby to było jednak wbrew duchowi gry (np. w grze gdzie ważne jest zapamiętywanie, używanie telefonów komórkowych do robienia zdjęć).
```

Dla ChatGPT, Claude, Perplexity i podobnych narzędzi najprostsze wejście to publiczny plik `llms-full.txt` albo pełny Markdown:

- <https://jfpio.github.io/harcerz-w-polu/llms.txt>
- <https://jfpio.github.io/harcerz-w-polu/llms-full.txt>
- <https://jfpio.github.io/harcerz-w-polu/book/harcerz-w-polu.md>
- <https://jfpio.github.io/harcerz-w-polu/book/harcerz-w-polu.txt>

MCP nie jest wymagany dla pierwszej wersji, bo książka jest publiczna, statyczna i mieści się w pojedynczym pliku tekstowym. MCP ma sens później, jeśli potrzebne będzie programowe wyszukiwanie po grach, zwracanie cytatów z lokalizacją albo integracja wielu książek.

## Praca lokalna

Wymagane są Node.js 24+, Python 3 oraz Poppler do przygotowania obrazów ze skanu.

```sh
npm install
npm run content
npm run qa
npm run build
npm run dev
```

Pełne ponowienie OCR wymaga zmiennej `MISTRAL_API_KEY` w lokalnym pliku `~/.secrets/mistral.env`:

```sh
npm run ocr
```

Pipeline zapisuje checkpoint co 20 stron, umożliwia wznowienie po limicie API, wyodrębnia ilustracje i usuwa tymczasowo przesłany plik z Mistrala po zakończeniu.

## Korekty

Na dole każdej strony znajduje się odsyłacz „Edytuj stronę”. Korekta powinna usuwać wyłącznie błąd rozpoznania OCR i zachowywać historyczną pisownię źródła. Przed wysłaniem zmiany należy uruchomić `npm run qa` oraz `npm run build`.

Szczegółowy raport pewności OCR znajduje się w `data/ocr/reports/`.
