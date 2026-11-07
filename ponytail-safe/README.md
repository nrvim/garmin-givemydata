# Ponytail Safe

Dit is Ponytail, de "luie senior developer"-modus voor Claude Code: de kleinste wijziging die het probleem echt oplost. Deze versie heeft een runtime die veiligheid voorop zet.
Het is een fork van [Ponytail 5.3.3](https://github.com/DietrichGebert/ponytail) (MIT) van Dietrich Gebert. De ruleset en de review-, audit- en debt-skills zijn ongewijzigd overgenomen. De hooks zijn opnieuw geschreven.

**Uitgangspunt:** standaard gaat er niets naar buiten, draait er geen onverwachte code, en gebeurt er alleen wat jij expliciet toestaat. Elke hook draait in de sandbox van Node, met alleen de mappen die hij nodig heeft.
Zie [SECURITY.md](SECURITY.md) voor de audit van het origineel, de maatregelen, de tests en de bekende grenzen.

## Installeren

Vereist: Claude Code en Node.js 22.13 of nieuwer (`node -v`). De Claude-app levert zelf geen `node` mee: zonder Node draaien de hooks niet en blijft bijvoorbeeld `/ponytail status` zonder antwoord.

```
/plugin marketplace add StephanH76/garmin-givemydata
/plugin install ponytail-safe@ponytail-safe
```

### Node.js installeren

- **macOS / Linux:** via https://nodejs.org (LTS), Homebrew (`brew install node`) of je pakketbeheerder.
- **Windows met adminrechten:** `winget install OpenJS.NodeJS.LTS`
- **Windows zonder adminrechten:** pak de zip-versie uit in je gebruikersmap en zet die in je eigen PATH. Controleer eerst of je werkgever dat toestaat. In PowerShell, zonder admin:

  ```powershell
  $v = "v26.13.0"   # of de nieuwste LTS van https://nodejs.org
  $dir = "$env:LOCALAPPDATA\Programs\node"
  $zip = "$env:TEMP\node-$v-win-x64.zip"
  Invoke-WebRequest -UseBasicParsing "https://nodejs.org/dist/$v/node-$v-win-x64.zip" -OutFile $zip
  $expected = ((Invoke-WebRequest -UseBasicParsing "https://nodejs.org/dist/$v/SHASUMS256.txt").Content -split "`n" | Where-Object { $_ -match "node-$v-win-x64.zip" }).Split(" ")[0]
  if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $expected.ToUpper()) { throw "Hash klopt niet, niet installeren" }
  Expand-Archive $zip -DestinationPath $dir -Force
  [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$dir\node-$v-win-x64", "User")
  ```

Sluit daarna je terminal en de Claude-app helemaal af (ook in het systeemvak), open ze opnieuw en controleer `node -v`.

### Werkt het niet?

Geeft `/ponytail status` geen dashboard, controleer dan eerst `node -v` (22.13 of nieuwer). Typ daarna `/ponytail doctor`: dat laat zien of de sandbox aanstaat en of de hook je datamap mag lezen en schrijven. Helpt dat niet, start Claude Code dan met `claude --debug` en zoek naar regels met `ponytail-safe:`.

Kent `/ponytail doctor` het commando niet, dan draai je nog een oude versie; zie hieronder.

### Bijwerken

`/reload-plugins` laadt alleen de versie die al gedownload is; een nieuwe versie haal je zo op.

- **Claude Code in de terminal:**

  ```
  claude plugin marketplace update ponytail-safe
  claude plugin update ponytail-safe@ponytail-safe
  ```

- **Claude desktop-app** (heeft geen update-knop, ook niet onder *Manage*):
  1. Verwijder de plug-in: *Settings → Customize → Plugins → Ponytail safe → ⋯ → Remove*.
  2. Sluit de app helemaal af, ook in het systeemvak.
  3. Verwijder de oude gedownloade kopieën. Je instellingen in `~/.config/ponytail-safe` blijven staan.

     ```powershell
     Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\plugins\cache\ponytail-safe" -ErrorAction SilentlyContinue
     Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\plugins\marketplaces\ponytail-safe" -ErrorAction SilentlyContinue
     ```

     Op macOS of Linux: `rm -rf ~/.claude/plugins/cache/ponytail-safe ~/.claude/plugins/marketplaces/ponytail-safe`
  4. Open de app en typ in een **lokale** sessie, dus niet in een cloudsessie, `/plugin marketplace add StephanH76/garmin-givemydata`. Installeer daarna "Ponytail safe" opnieuw.

Controleer de versie in de map `~/.claude/plugins/cache/ponytail-safe/ponytail-safe/`. Die moet overeenkomen met `version` in `.claude-plugin/plugin.json`. Daarna laat `/ponytail doctor` zien of alles werkt.

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
| `/ponytail doctor` | Wat de sandbox de hooks toestaat: om een installatie te controleren. |
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

22 tests, waaronder de sandbox, het startscript, een netwerk- en subprocess-tripwire, prompt-injectie, de guard en CSV-injectie. Zie SECURITY.md voor de volledige lijst en de mutatietest.
