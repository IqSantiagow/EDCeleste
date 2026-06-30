---
name: textual-debug
description: Uruchamia aplikację Textual w trybie debugowania — konsola debugowania i aplikacja działają równolegle na porcie 7342.
---

Uruchom aplikację Textual w trybie debugowania, uruchamiając równolegle konsolę Textual i aplikację.

## Kroki

1. Uruchom w tle konsolę debugowania Textual z filtrowaniem zdarzeń EVENT:
   ```
   textual console -x EVENT --port 7342
   ```

2. Równolegle uruchom aplikację w trybie deweloperskim (nie czekaj na zakończenie konsoli):
   ```
   textual run --dev --port 7342 app.py
   ```

Obie komendy uruchamiaj jako procesy w tle (`run_in_background: true`), żeby działały jednocześnie. Konsolę uruchom jako pierwszą, chwilę poczekaj (kilka sekund), a potem uruchom aplikację — tak żeby konsola była gotowa przed podłączeniem się aplikacji.

Gdy procesy zostaną uruchomione, poinformuj użytkownika, że:
- konsola Textual nasłuchuje na porcie 7342 (z filtrowaniem zdarzeń EVENT)
- aplikacja działa w trybie `--dev` i wysyła logi do konsoli
- żeby zatrzymać — niech zamknie oba procesy (Ctrl+C w odpowiednich terminalach)