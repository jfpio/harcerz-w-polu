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
