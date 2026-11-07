# Datovka Multibox

Místní MCP konektor pro více českých datových schránek. Odvozeno z projektu
[Sensio-cz/mcp-datovka](https://github.com/Sensio-cz/mcp-datovka), viz [UPSTREAM.md](UPSTREAM.md).

Verze 0.2.0 je základ připravený pro doplnění vlastních účtů. Offline testy
ověřují ochrany a sestavení SOAP požadavků. Funkčnost s opravdovými schránkami
zatím nebyla ověřena. Před ostrým provozem proveďte zkoušku v testovacím ISDS.

## Veřejná a soukromá varianta

Veřejná část je tento repozitář: zdrojový kód, plugin, testy a vzor konfigurace.
Soukromá varianta používá stejné jádro s místním nastavením. Nevzniká druhá větev
s hesly, kterou by bylo možné omylem sloučit do veřejné verze.

Na Windows jsou účty a návrhy standardně v `%LOCALAPPDATA%\DatovkaMultibox`.
Na ostatních systémech v `~/.local/share/DatovkaMultibox`. Umístění lze změnit
absolutní cestou v `DATOVKA_PRIVATE_DIR`; musí být mimo repozitář.
Hesla ukládá knihovna keyring do systémového úložiště (na Windows Credential
Manager). Hesla nejsou v JSON, argumentech nástrojů ani v konfiguraci MCP.
Soubor `config.example.json` obsahuje pouze smyšlený příklad.

## Instalace na Windows

Potřebujete Python 3.11 nebo novější. V kořeni projektu spusťte:

```powershell
./scripts/install.ps1
./scripts/nastavit-ucet.ps1
```

První příkaz vytvoří oddělené `.venv` a prázdnou soukromou konfiguraci.
Druhý interaktivně přidá účet; lze ho opakovat pro další schránky. Heslo se
zadává skrytě v místním terminálu. Testovací prostředí je výchozí, produkční
se volí výslovně. Příjem i odesílání se povolují zvlášť. Přidání účtu se
nepřipojuje k ISDS a není ověřením správnosti přihlašovacích údajů.

Současná verze podporuje jméno a heslo ISDS. Bankovní identita, Mobilní klíč,
SMS a certifikát v této verzi implementované nejsou. Neměňte si kvůli tomu
bez rozmyslu nastavení zabezpečení účtu.

## Připojení k AI klientovi

Balíček obsahuje kompatibilní manifest `.codex-plugin/plugin.json`, `.mcp.json`
a dovednost v `skills/`. Po instalaci závislostí lze kořen projektu přidat jako
místní plugin. Instalace uloží cestu k běhovému prostředí do soukromého
`runtime.json`, aby fungovala i kopie pluginu v mezipaměti klienta.
Samotné zveřejnění na GitHubu jej nenainstaluje do Codexu ani
nezveřejní v katalogu OpenAI.

Pro běžného MCP klienta použijte absolutní cestu k
`.venv/Scripts/python.exe` (Windows), argumenty `-m mcp_datovka` a stdio.
Soukromá data nejsou součástí pluginu. Na Linuxu vytvořte `.venv` pomocí
`python3 -m venv .venv`, instalujte `.venv/bin/python -m pip install .` a
zajistěte funkční systémové úložiště hesel a Tk pro kontrolní okno.

## Práce se schránkami

- `datovka_list_boxes`: místní seznam účtů bez sítě.
- `datovka_list_received`, `datovka_list_sent`: seznamy z výslovně zvolené schránky.
- `datovka_read_message`: stažení přijaté zprávy včetně příloh v base64.
- `datovka_search_box`: hledání příjemce přes zvolený účet.
- `datovka_prepare_message`: místní neměnný návrh, bez odeslání.
- `datovka_get_draft`: celý text, odesílatel, příjemce, přílohy a stav.
- `datovka_send_draft`: jediný pokus o odeslání schváleného návrhu.

U příloh lze do JSON pole `files` zadat buď `file_path` s absolutní cestou,
nebo `filename`, `mime_type` a `content_base64`. Při přípravě se obsah uloží
do návrhu; pozdější změna původního souboru odesílaný návrh nezmění.
Text je příloha `text-zpravy.txt`, i když zpráva obsahuje další soubory.
Místní limit je 20 MiB a 50 přidaných příloh, nikoli tvrzení o limitu ISDS.

## Kontrola a odeslání

1. Připravte návrh a zkontrolujte schránku, prostředí, ID příjemce a obsah.
2. Otevřete místní kontrolní okno:

   ```powershell
   ./.venv/Scripts/python.exe -m mcp_datovka.setup review ID_NAVRHU
   ```

3. Uživatel v okně schválí konkrétní návrh. Schválení samo nic neodesílá.
4. AI může zavolat `datovka_send_draft` pouze s ID schváleného návrhu.

Návrh čeká na schválení nejvýše 24 hodin; po schválení platí 15 minut.
Odesílatel je svázán s ID schránky, přihlašovacím jménem a prostředím.
Před odesláním se přes ISDS kontroluje, zda přihlášení odpovídá ID schránky.
Jakákoli změna obsahu vyžaduje nový návrh a nové schválení.

Stav `sent` znamená, že ISDS vrátilo ID zprávy; není to potvrzení jejího
doručení adresátovi. `sending` po pádu procesu a `uncertain` po chybě vyžadují
ruční kontrolu odeslaných zpráv. Automatický druhý pokus je blokován.
Záměrně tu není nástroj MCP pro schválení. Jde o ochranu na hranici MCP,
nikoli proti programu se stejnými plnými právy k místním souborům a klávesnici.

## Doručení a soukromí

Načtení příchozích zpráv může způsobit doručení a běh lhůt. Vypnuté odesílání
tomu samo nebrání. Příjem se proto povoluje zvlášť. Není tu automatický
plánovač synchronizace. Viz [příručka Datovky](https://www.datovka.cz/datovka-docs/datovka/manual).

Návrhy a jejich přílohy jsou v místní SQLite databázi bez aplikačního šifrování;
chraňte uživatelský profil a disk. Hesla jsou v systémovém úložišti zvlášť.
Obsah vrácený MCP klientovi může být odeslán jeho poskytovateli AI podle
nastavení klienta. Místní server sám neznamená, že obsah zůstává pouze v PC.
Archivace ZFO, doručenek a zálohování na NAS zatím nejsou implementované.

## Vývoj a ověření

```powershell
./.venv/Scripts/python.exe -m pip install pytest build
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m build --wheel
```

Testy používají smyšlené účty a blokují síťové požadavky. Ověřují výběr účtu,
povolování příjmu, neměnnost návrhu, expiraci, souběh, blokování opakovaného
odeslání, chyby ISDS a skládání příloh. CI běží na Windows a Linuxu.

Licence původního kódu: MIT, viz LICENSE. Původ převzatých definic WSDL/XSD
a odlišné licence závislostí jsou uvedeny v UPSTREAM.md.
