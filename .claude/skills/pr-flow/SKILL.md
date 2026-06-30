---
name: pr-flow
description: Tworzy PR, monitoruje pipeline CI i code review od Claude, zarządza poprawkami iteracyjnie — od commitu do merge-ready
---

Przeprowadź pełny cykl PR dla bieżącego brancha. Wykonuj kroki po kolei.

## Krok 1 — Sprawdź stan

```bash
git status
git diff HEAD
```

Upewnij się, że:
- Branch to `feature/*` lub `fix/*` — nie `main`
- Są zmiany do commitu

## Krok 2 — Commit

Wystaw commit z konkretnym opisem (co zmieniono i dlaczego). Dodawaj tylko pliki powiązane z bieżącą zmianą — nigdy `git add .` ani `git add -A`.

**BEZWZGLĘDNY ZAKAZ:** Żadnego `Co-Authored-By:` ani żadnego innego trailera. Commit message kończy się po opisie, bez dodatkowych linii.

```bash
git add <konkretne pliki>
git commit -m "$(cat <<'EOF'
<tytuł commitu — co i dlaczego>
EOF
)"
```

## Krok 3 — Push

```bash
git push -u origin HEAD
```

## Krok 4 — Utwórz PR (jeśli nie istnieje)

Sprawdź czy PR już istnieje:
```bash
gh pr view 2>/dev/null && echo "PR EXISTS" || echo "NO PR"
```

Jeśli PR nie istnieje, utwórz go. Tytuł ≤70 znaków. BEZ Co-Authored-By w treści:

```bash
gh pr create --title "<tytuł>" --body "$(cat <<'EOF'
## Summary
- <co zostało zmienione>
- <dlaczego / jaki problem rozwiązuje>

## Test plan
- [ ] Lint i testy przechodzą
- [ ] <specyficzne kroki do sprawdzenia zmiany>
EOF
)"
```

Zanotuj numer PR — będzie potrzebny do pobierania komentarzy.

## Krok 5 — Monitoruj pipeline

Czekaj na zakończenie wszystkich checks. Joby wykonują się sekwencyjnie: `lint → test → claude-review`.

```bash
gh pr checks --watch
```

Jeśli `--watch` nie kończy działania normalnie, polluj co ~30 sekund:
```bash
gh pr checks
```

### Krok 5a — Błąd lint

Gdy job `lint` failuje:

1. Pobierz szczegóły błędu:
   ```bash
   gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId' | xargs gh run view --log-failed
   ```

2. Auto-napraw lokalnie:
   ```bash
   ruff check --fix
   ruff format
   ```

3. Commit poprawek i push, następnie wróć do kroku 5:
   ```bash
   git add <naprawione pliki>
   git commit -m "Fix lint errors"
   git push
   ```

### Krok 5b — Błąd testów

Gdy job `test` failuje:

1. Pobierz logi:
   ```bash
   gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId' | xargs gh run view --log-failed
   ```

2. Odtwórz błąd lokalnie:
   ```bash
   coverage run -m unittest discover
   coverage report -m
   ```

3. Zidentyfikuj i napraw przyczyny błędów. Commit poprawek i push, następnie wróć do kroku 5.

## Krok 6 — Pobierz i podsumuj code review od Claude

Gdy `claude-review` zakończy się sukcesem, pobierz komentarze:

```bash
# Ogólne komentarze do PR (tutaj Claude wstawia Summary)
gh pr view --json comments --jq '.comments[] | "=== [\(.author.login)] ===\n\(.body)\n"'

# Komentarze inline do linii kodu
PR_NUM=$(gh pr view --json number --jq .number)
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api "repos/$REPO/pulls/$PR_NUM/comments" --jq '.[] | "[\(.path):\(.line // .original_line)] \(.body)"'
```

Na podstawie zebranych danych wyprowadź zwięzłe podsumowanie po polsku:

```
## Wynik code review

**Status:** Zatwierdzone / Zmiany wymagane

**Co jest OK:**
- <lista zaakceptowanych rzeczy lub "Brak uwag do bieżących zmian">

**Issues do rozważenia:**
1. [plik:linia] (bug|security|performance) — opis — proponowana poprawka
2. ...

**Maintenance notes (opcjonalne):**
- ...
```

Następnie **zapytaj użytkownika**, które issues naprawić. Poczekaj na odpowiedź przed kontynuowaniem.

## Krok 7 — Wdróż zatwierdzone poprawki

Na podstawie decyzji użytkownika napraw **tylko** to, co zostało zatwierdzone. Commit i push:

```bash
git add <zmienione pliki>
git commit -m "Address code review: <co poprawiono>"
git push
```

Wróć do **kroku 5** — monitoruj nowy run pipeline'a.

## Krok 8 — Zakończenie

Gdy pipeline przejdzie w całości i review jest pozytywny (lub "No issues found"):

Poinformuj użytkownika: PR jest merge-ready. Podaj link do PR:
```bash
gh pr view --json url --jq .url
```

**Nie merguj samodzielnie.** Czekaj na decyzję użytkownika.
