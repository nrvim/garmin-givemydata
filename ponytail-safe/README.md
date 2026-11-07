# Ponytail Safe

Dit is Ponytail, de "luie senior developer"-modus voor Claude Code: de kleinste wijziging die het probleem echt oplost. Deze versie heeft een runtime die veiligheid voorop zet.
Het is een fork van [Ponytail 5.3.3](https://github.com/DietrichGebert/ponytail) (MIT) van Dietrich Gebert. De ruleset en de review-, audit- en debt-skills zijn ongewijzigd overgenomen. De hooks zijn opnieuw geschreven.

**Uitgangspunt:** standaard gaat er niets naar buiten, draait er geen onverwachte code, en gebeurt er alleen wat jij expliciet toestaat. Elke hook draait in de sandbox van Node, met alleen de mappen die hij nodig heeft.
Zie [SECURITY.md](SECURITY.md) voor de audit van het origineel, de maatregelen, de tests en de bekende grenzen.

## Installeren

Vereist: Claude Code en Node.js 22.13 of nieuwer (`node -v`).

```
/plugin marketplace add StephanH76/garmin-givemydata
/plugin install ponytail-safe@ponytail-safe
```

In deze repo staat Ponytail Safe al aan via `.claude/settings.json`: Claude Code vraagt bij het openen van de repo of je de marketplace vertrouwt en installeert de plug-in daarna.

Eerst proberen zonder te installeren, alleen voor één sessie:

```
claude --plugin-dir ./ponytail-safe
```

## Gebruik

| Commando | Wat het doet |
|----------|--------------|
| `/ponytail [lite\|full\|ultra\|off]` | Codeermodus voor deze sessie. `full` is de standaard. "stop ponytail" zet hem uit. |
| `/ponytail status` | Dashboard: niveau, functies, kosten, tokens en beurten per project. |
| `/ponytail level safe\|controlled\|developer` | Veiligheidsniveau. Blijft bewaard. |
| `/ponytail allow <functie>` / `/ponytail deny <functie>` | Toestemming per functie. |
| `/ponytail default lite\|full\|ultra\|off` | De modus waarin nieuwe sessies starten. |
| `/ponytail import` / `/ponytail import apply` | Oude sessies importeren: eerst een dry run, dan echt (alleen op developer-niveau). |
| `/ponytail-review`, `/ponytail-audit`, `/ponytail-debt`, `/ponytail-gain`, `/ponytail-help` | De skills uit Ponytail. |

Een commando telt alleen als het je **hele** prompt is, op één regel. "Kun je /ponytail allow import doen?" of een geplakt blok tekst verandert dus niets.

## Veiligheidsniveaus

| Functie | safe | controlled | developer | Wat het doet |
|---------|:----:|:----------:|:---------:|--------------|
| ruleset | ✓ | ✓ | ✓ | De Ponytail-regels in de context. |
| `subagents` | ✓ | ✓ | ✓ | Dezelfde regels voor subagents. |
| `ledger` | ✓ | ✓ | ✓ | Kosten, tokens en beurten van de huidige sessie, alleen cijfers, lokaal. |
| `audit` | – | ✓ | ✓ | Lokale auditlog van elke hook-actie (zonder prompttekst). |
| `map` | – | allow | allow | Namen van functies en klassen in je project, bij de sessiestart. |
| `names` | – | – | allow | De eerste regel van je eerste prompt als taaknaam in het grootboek. |
| `import` | – | – | allow | Usage-cijfers uit oude sessies van alle projecten. |

"allow" betekent: het niveau staat het toe, maar het blijft uit tot je `/ponytail allow <functie>` typt.
Bij het overstappen naar `developer` krijg je een waarschuwing. Elke wijziging van niveau of toestemming komt altijd in `audit.jsonl`.

## Waar staat wat

Alles staat lokaal, in `~/.config/ponytail-safe/` (`$XDG_CONFIG_HOME` wordt gerespecteerd). De map staat op 0700, de bestanden op 0600.

- `config.json`: niveau, standaardmodus, toestemmingen (met tijdstip)
- `ledger.csv`: één regel per sessie
- `audit.jsonl`: auditlog, roteert bij 1 MB
- `modes/`, `active`: de huidige modus per project

Alles resetten: verwijder die map. Plug-in verwijderen: `/plugin uninstall ponytail-safe@ponytail-safe`.

## Statusline (optioneel, stel je zelf in)

Voeg aan `~/.claude/settings.json` toe:

```json
"statusLine": { "type": "command", "command": "bash /PAD/NAAR/ponytail-safe/hooks/statusline.sh" }
```

## Tests

```
node --test ponytail-safe/tests/*.test.js
```

18 tests, waaronder de sandbox, een netwerk- en subprocess-tripwire, prompt-injectie, de guard en CSV-injectie. Zie SECURITY.md voor de volledige lijst en de mutatietest.
