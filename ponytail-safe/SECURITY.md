# Ponytail Safe: beveiligingsrapport

Audit van Ponytail 5.3.3 (tag `v5.3.3`, commit `7801d061`, 29 oktober 2026) en wat Ponytail Safe 1.0.0 daaraan verandert.
Alleen het Claude Code-deel is geaudit: `hooks/`, `skills/`, `.claude-plugin/` en de band-module.
De integraties voor Cursor, Codex, Copilot, Qoder en andere hosts zijn niet meegenomen; Ponytail Safe ondersteunt alleen Claude Code.

## 1. Bevindingen in Ponytail 5.3.3

Er is geen kwaadaardige code gevonden. De auteur escapet HTML, eist https voor de webhook en filtert shell-tekens uit paden.
Wel ruim de risico's hieronder. Ernst: H = hoog, M = middel, L = laag.

| # | Ernst | Waar | Wat |
|---|-------|------|-----|
| 1 | H | `hooks/band/register.tsx` | De band-module onderschept **elke** Bash-, Edit- en Write-aanroep van de agent en leest bij Write het oude bestand. |
| 2 | H | `register.tsx` `findTranscript` | Doorzoekt na elke beurt **alle** mappen in `~/.claude/projects` (alle projecten) en draait `grep` op het transcript. |
| 3 | H | `ponytail-band-import.js` | `/ponytail band import` start een losgekoppeld achtergrondproces dat de transcripts van **alle** sessies in **alle** projecten leest, inclusief subagents en de eerste 500 tekens van prompts. |
| 4 | M | `register.tsx` `record` | Standaard aan: de eerste regel van je eerste prompt komt als taaknaam in platte tekst in `~/.config/ponytail/band/<project>.csv`. |
| 5 | M | `register.tsx` `record` | Optionele webhook: elke beurt een POST met kosten, tokens en taaknaam naar een zelfgekozen URL. Standaard leeg. |
| 6 | M | `ponytail-activate.js` | Kopieert bij elke sessiestart een shellscript naar `~/.claude/` en geeft het model de opdracht om "proactief aan te bieden" je globale `~/.claude/settings.json` aan te passen. |
| 7 | M | `ponytail-map.js` | Leest bij elke sessiestart tot 4000 bronbestanden via `git ls-files` (subprocess), zonder dat je dat hebt aangezet. |
| 8 | M | `register.tsx` | Draait bij elke sessiestart en elke beurt `git grep --untracked` over het hele project, en `xdg-open`/`open`/`cmd start` voor het board. |
| 9 | L | `band-import`, `register.tsx` | CSV-velden worden gequote, maar een naam die met `=`, `+`, `-` of `@` begint, wordt in Excel of Sheets als formule uitgevoerd (CSV-injectie). |
| 10 | L | algemeen | Alle hooks draaien met de volledige rechten van je gebruikersaccount: lezen en schrijven overal, subprocessen en netwerk. |
| 11 | L | algemeen | Niets weerhoudt de agent ervan de config van Ponytail zelf aan te passen (bijvoorbeeld een webhook-URL zetten). |

## 2. Wat Ponytail Safe anders doet

| Bevinding | Maatregel |
|-----------|-----------|
| 1, 2, 8 | De band-module is verwijderd. Geen hook kijkt mee met tool-aanroepen, behalve `guard.js`, en die leest niets: hij bekijkt alleen het pad of commando in het geheugen. |
| 2 | `stop.js` leest alleen het transcript dat Claude Code zelf meegeeft, en alleen als het echte pad (na het oplossen van symlinks) binnen `~/.claude/projects` ligt. |
| 3 | Import staat standaard uit. Hij vraagt niveau `developer` **en** `/ponytail allow import`, draait alleen als jij `/ponytail import apply` typt, geeft eerst een dry run die niets leest, en draait zonder achtergrondproces met een limiet van 20 seconden. |
| 4 | Er wordt geen prompttekst opgeslagen, behalve op niveau `developer` na `/ponytail allow names`. |
| 5 | Geen webhook en geen netwerkcode. Afgedwongen door een statische test en door een tripwire in de tests. |
| 6 | Er wordt niets in `~/.claude` geschreven en het model krijgt geen opdracht om je instellingen te wijzigen. De statusline is optioneel en stel je zelf in. |
| 7 | De map staat standaard uit. Hij vraagt niveau `controlled` plus `/ponytail allow map`. Het is een gewone mappenwandeling zonder `git`, met limieten (1500 bestanden, diepte 6, 64 KB per bestand, 1,5 seconde), en slaat verborgen mappen, symlinks en bestanden met *secret*, *credential*, *password*, *token* of *private* in de naam over. Hij weigert je thuismap en `/`. |
| 9 | `csvField` zet een `'` voor velden die met `= + - @` of een tab/CR beginnen. |
| 10 | Elke hook draait onder `node --permission` (het permissiemodel van Node) met alleen de mappen die hij nodig heeft. Subprocessen, workers en native addons zijn daardoor op runtime-niveau geblokkeerd. Zie de tabel hieronder. |
| 11 | Niveau en toestemming veranderen alleen via een prompt die jij typt en die **in zijn geheel** het commando is. De ruleset verbiedt het model de bestanden aan te raken, en `guard.js` weigert Edit-, Write- en Bash-aanroepen die erin schrijven. |

### Rechten per hook (afgedwongen door Node)

| Hook | Mag lezen | Mag schrijven |
|------|-----------|---------------|
| SessionStart (`session-start.js`) | plug-in, `~/.config/ponytail-safe`, projectmap | `~/.config/ponytail-safe` |
| UserPromptSubmit (`prompt.js`) | plug-in, `~/.config/ponytail-safe`, `~/.claude/projects` | `~/.config/ponytail-safe` |
| Stop (`stop.js`) | plug-in, `~/.config/ponytail-safe`, `~/.claude/projects` | `~/.config/ponytail-safe` |
| SubagentStart (`subagent.js`) | plug-in, `~/.config/ponytail-safe` | niets |
| PreToolUse (`guard.js`) | alleen de plug-in | niets |

De OS-grens is grover dan de code. SessionStart mag bijvoorbeeld de projectmap lezen, maar de code doet dat alleen als de map aanstaat.
Beide lagen worden apart getest.

## 3. Bewijs: tests

`node --test ponytail-safe/tests/*.test.js` draait 18 tests. Ze voeren het **echte** commando uit `hooks/hooks.json` uit via bash, dus mét de sandbox-vlaggen, in een tijdelijke nep-thuismap.
Elke hook-run draait met `tests/tripwire.js` ervoor geladen: dat meldt en blokkeert elke aanroep van `net`, `tls`, `http(s)`, `http2`, `dgram`, `dns`, `child_process`, `fetch` en `WebSocket`.

| Garantie | Test |
|----------|------|
| Runtime-code gebruikt alleen `fs`, `path`, `os`, `crypto`, `string_decoder` | statische scan, ook op `eval`, `new Function`, dynamische `import()`/`require` |
| Elke hook draait onder `node --permission`, schrijft alleen in zijn eigen map, krijgt geen subprocess-, worker- of addon-rechten | manifestcontrole |
| De sandbox en de tripwire werken echt | twee positieve controles: een probe die buiten de sandbox leest krijgt `ERR_ACCESS_DENIED`, een `https.get` wordt gevangen |
| Safe: geen map, geen audit, geen schrijfacties buiten de eigen map | bestandsboom vóór en na vergeleken |
| Het grootboek bevat geen prompt- of antwoordtekst, staat op 0600 en rekent kosten correct | nep-transcript met geheime tekst |
| Transcripts buiten `~/.claude/projects` of via een symlink worden geweigerd | via de sandbox én via de code apart |
| Een commando midden in een zin, of in een geplakt blok van meerdere regels, verandert niets | prompt-injectiegevallen |
| De agent kan config, grootboek en audit niet bewerken via Edit, Write of Bash | guard-tests, inclusief `../`-paden en pipes |
| Map en import vragen elk hun niveau plus aparte toestemming; deny zet ze weer uit | controlled- en developer-tests |
| CSV-injectie wordt onschadelijk gemaakt | `=HYPERLINK(...)` als taaknaam |
| Kapotte input of een kapotte config faalt dicht en snel (exit 0, < 5 s); een kapotte config telt als `safe` | robuustheidstest |
| Modi, standaardmodus, stoppen, dashboard en subagents werken zoals in Ponytail | functionele test |

**Mutatietest.** Om te laten zien dat de tests ook echt iets vangen, zijn er elf bewuste lekken ingebouwd in een kopie:
sandbox weg, prompttekst opslaan, geplakte blokken accepteren, commando's midden in een zin accepteren, symlinks toestaan, map zonder toestemming, een `https.get` toevoegen, geen CSV-bescherming, guard uit, `allow` zonder niveaucheck, en prompttekst in de auditlog.
Na het toevoegen van de defence-in-depth-test vangen de tests ze alle elf.

**End-to-end in Claude Code 2.1.319** (geïsoleerd met `--plugin-dir` en een tijdelijke `XDG_CONFIG_HOME`):

- `/ponytail status` toonde het dashboard. Het grootboek gaf $0.1447, precies het bedrag dat Claude Code zelf rapporteerde.
- Gevraagd om de config naar `developer` te zetten, weigerde het model (laag 1).
- Expliciet gevraagd een Write-aanroep naar de datamap te *proberen*, werd die geblokkeerd door de guard-hook (laag 2). Het bestand is niet ontstaan.
- `/ponytail level controlled` en daarna `/ponytail allow map`: pas vanaf dat moment stond de codebase-map in de context, en alles staat in de auditlog.

## 4. Bekende grenzen (eerlijk)

- **Node 22.13 of nieuwer is vereist**, voor `--permission`. Op een oudere Node faalt de hook en injecteert hij niets (dicht falen). Windows zonder bash wordt niet ondersteund, omdat de commando's `${VAR:-default}` gebruiken.
- **Het permissiemodel van Node beperkt bestanden, subprocessen en workers, maar geen netwerk.** Dat er geen netwerkverkeer is, rust op de statische scan en de tripwire-tests, niet op een runtime-blokkade.
- **De guard werkt op patronen.** Een eerder aangemaakte symlink naar de datamap, of een verhuld shellcommando (bijvoorbeeld base64), kan erlangs. Hij is een tweede verdedigingslinie. De eerste is dat toestemming alleen uit een getypte prompt komt.
- **De auditlog is niet fraudebestendig.** Wie als jouw gebruiker schrijfrechten heeft, kan hem aanpassen. Hij is bedoeld voor overzicht, niet voor forensisch onderzoek.
- **Kostenschattingen** gebruiken de prijstabel uit Ponytail 5.3.3. Bij een onbekend model staat de kolom leeg.
- **Wat uit Ponytail is weggevallen:** de grafische band boven de prompt (met knoppen), het HTML-board, het meten van hergebruik en open callers, de test-status in de band, de webhook, en de integraties voor andere agents. Het dashboard is nu tekst (`/ponytail status`).
- Deze fork volgt de updates van upstream Ponytail niet automatisch. Nieuwe upstream-versies moeten opnieuw geaudit en handmatig overgenomen worden.
