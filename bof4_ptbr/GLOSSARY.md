# Breath of Fire IV (PC) — PT-BR Translation Glossary & Style Guide

> **Scope & Golden Rule:** This glossary is the single source of truth for all 8 parallel translators working on `bof4_ptbr/corpus/shard_01..08.json`. Every translator **MUST** translate 100% from scratch from each entry's `"en"` field into natural, idiomatic **Brazilian Portuguese (PT-BR)** using **full native Portuguese accents** (`á à â ã é ê í ó ô õ ú ç Á À Â Ã É Ê Í Ó Ô Õ Ú Ç º ª`).
>
> **FORBIDDEN:** Never edit `"locked": true` entries. Never copy, consult, or import text from `port_translation.py` or any PS1 translation.

---

## 1. Locked English Proper Names (A2–A4 Rule — KEEP IN ENGLISH!)

Even inside **unlocked** PT-BR dialogues, descriptions, tutorials, and menus, **ALWAYS keep these proper names in their original English spelling** (translating only surrounding Portuguese articles, prepositions, and prose):

1. **Items, Consumables, Weapons, Armor, Accessories, Key Items, Rods, Lures & Fish:**
   - All `INIT.DAT[7]` catalog entries and any `{CAT:SS:II}` references stay in English (e.g., `Healing Herb`, `Vitamin`, `Aurum`, `Skill Ink`, `King's Sword`, `Flame Sword`, `Ring of Ice`, `Master's Rod`, `Sluice Key`, `Fire Gem`, `Manillo`, fish species).
   - Example: `"Switching skills requires 1 {COLOR:02}{CAT:00:23}{/COLOR}."` → `"Trocar habilidades exige 1 {COLOR:02}{CAT:00:23}{/COLOR}."`
   - Note: `Skill Scroll` (the UI concept in `CAMP.DAT`) may be translated as **Pergaminho de Habilidades** (or **Perg. Habilidades** when tight on pixels).

2. **Spells, Skills, Combos, Dragon Forms & Master Wills:**
   - Keep spell/skill/combo names in English: `Flare`, `Fireblast`, `Inferno`, `Sever`, `Frost`, `Heal`, `Peep`, `Shadowwalk`, `Super Combo`, `Aura`, `Kaiser`, `Wyvern`, `Behemoth`, `Astral`, `Myrmidon`, `Weyr`, `Tyrant`, etc.
   - Keep all **12 Master Wills** in English (including before the colon in `CAMP.DAT[5]` Will descriptions):
     `Haste`, `Drowse`, `Finale`, `Reck`, `Pique`, `Ward`, `Filch`, `Wild`, `Vision`, `Guard`, `Valor`, `Greed`.
     - Example: `"Haste: Increases speed in combat"` → `"Haste: Aumenta vel. em combate"` (205px ≤ 228px)

3. **Party Members, Masters, NPCs & Monsters:**
   - **7 Party Members (always English, usually referenced via `{CHAR:00..06}`):**
     `Ryu` (`00`), `Nina` (`01`), `Cray` (`02`), `Scias` (`03`), `Ursula` (`04`), `Ershin` (`05`), `Fou-Lu` (`06`).
   - **12 Masters (locked English):**
     `Rwolf`, `Momo`, `Kryrik`, `Abbess`, `Njomo`, `Gyosil`, `Stoll`, `Una`, `Bunyan`, `Lyta`, `Kahn`, `Marlok`.
   - **Key Story NPCs (keep original names):**
     `Elina`, `Yuna`, `Rasso`, `Yohm`, `Mami`, `Deis`, `Won-qu`, `Kahbo`, `Kurok`, `Sonia`, `Garr`, `Poko`, `Tarhn`, `Soniel`.
   - **All 177 Monsters & Bosses:** keep original English names verbatim (`Mage Goo`, `Army Bat`, `Blue Cap`, `Bolt Trp`, `Eye Goo`, `Kahn`, `Tyrant`, etc.).

4. **Cities, Regions, Landmarks & Fishing Spots:**
   - Keep proper place names verbatim in English:
     `Synesta`, `Sarai`, `Windia`, `Chiqua`, `Ludia`, `Shyde`, `Chedo`, `Astana`, `Pauk`, `Saldine`, `Shikk`, `Chamba`, `Kyoin`, `Lyp`, `Kurok`, `Ahm Fen`, `Worent`, `Saneffi`, `Soniel`, `Tscha`, `Pabu Pabu`, `Imperial Capital` (see geopolitical terms below).
   - **Geopolitical Factions (translate generic nouns, keep proper stems):**
     - `Fou Empire` → **Império Fou** (and `the Empire` → **o Império**; `Imperial` → **Imperial**)
     - `Eastern Alliance` / `the Alliance` → **Aliança do Leste** / **a Aliança**
     - `Western Continent` / `Eastern Continent` → **Continente Ocidental** / **Continente Oriental**
     - `Emperor's Tomb` → **Tumba do Imperador** (when inside dialogue prose; locked map-slot names stay untouched)

---

## 2. Standardized PT-BR Terminology Table

Use these exact translations consistently across all 8 shards so menus, tutorials, descriptions, and dialogues match seamlessly:

### A. Title Screen, Menus, Camp & System UI
*(Note: `BOF4.exe` title/HUD strings are already patched to: `NOVO JOGO`, `CARREGAR`, `OPÇÕES`, `MELHOR`, `NOVO RECORDE`, compass `N/S/L/O`.)*

| English | PT-BR Standard | Short / Tight-Budget Form |
| :--- | :--- | :--- |
| New Game / Load Game / Option | Novo Jogo / Carregar / Opções | — |
| Main Menu / Title Screen | Menu Principal / Tela Título | — |
| Camp / Rest | Acampamento / Descansar | Acamp. |
| Status / Special / Equip / Item | Status / Especial / Equipar / Itens | Equip. |
| Change / Switch / Setting | Trocar / Alternar / Configuração | Config. |
| Save / Load / Quit / Exit / Cancel | Salvar / Carregar / Sair / Cancelar | — |
| Yes / No / Back / Help / List | Sim / Não / Voltar / Ajuda / Lista | — |
| Look / Add / Uniq / Info / Join | Ver / Adicionar / Única / Info / Entrar | Adic. |
| Master / Apprentice / Will | Mestre / Aprendiz / Vontade | — |
| Skill / Skill Scroll | Habilidade / Pergaminho de Habilidades | Hab. / Perg. Hab. |
| Formation / Order / Row | Formação / Ordem / Fileira | — |
| Buy / Sell / Trade / Exchange | Comprar / Vender / Trocar / Câmbio | — |
| Search / Explore / Map / Cast | Vasculhar / Explorar / Mapa / Lançar | — |
| Sail / DropSail / Anchor | Navegar / Içar Vela / Ancorar | — |
| Key/Pad Setting | Config. Teclado/Controle | — |
| EMPTY / FREE | VAZIO / LIVRE | — |

### B. Battle System, Stats, Elements & Status Effects

| English | PT-BR Standard | Short / Tight-Budget Form |
| :--- | :--- | :--- |
| Rotation System | Sistema de Rotação | — |
| Front Rank / Rear Rank | Linha de Frente / Retaguarda | Frente / Retag. |
| Attack / Special / Use Item / Guard | Atacar / Especial / Usar Item / Defender | — |
| Charge / Escape / Flee | Investida / Fugir | — |
| Examine / Peep | Examinar / `Peep` *(skill name stays EN)* | — |
| Combo / Combo Attack | Combo / Ataque Combo | — |
| Counter / Reprisal | Contra-ataque / Represália | Contra-atq. |
| Critical Hit / Lucky Strike | Golpe Crítico / Golpe de Sorte | Crítico |
| Instant Kill / Instant Death | Morte Instantânea | Morte Inst. |
| Initiative / Caught by surprise | Iniciativa / Pegos de surpresa | — |
| HP / AP / CP / EXP / LV / Zenny | HP / AP / CP / EXP / NV (ou LV) / Zenny (`{ZENNY}`) | Keep `HP`, `AP`, `CP`, `EXP`, `{ZENNY}` |
| Power (`Pwr`) / Defense (`Def`) | Poder (`FOR`) / Defesa (`DEF`) | `FOR` / `DEF` |
| Agility (`Agl`) / Wisdom (`Wis`) / Weight (`Wgt`) | Agilidade (`AGI`) / Sabedoria (`SAB`) / Peso (`PES`) | `AGI` / `SAB` / `PES` |
| Target (`one` / `all`) | Alvo (`um` / `todos`) | `1 alvo` / `todos` |
| Fire / Wind / Water / Earth / Holy / Death | Fogo / Vento / Água / Terra / Sagrado / Morte | `Fog` / `Ven` / `Águ` / `Ter` |
| `Fir+Win` / `Win+Wat` / `Wat+Ear` / `Ear+Fir` | `Fog+Ven` / `Ven+Águ` / `Águ+Ter` / `Ter+Fog` | — |
| Mind / Stat / Slash / Ranged / Magic / Dragon | Mental / Estado / Corte / Distância / Magia / Dragão | — |
| `ST Change` / `ST Down` / `ST Up` / `LV Up` | `Alt. Status` / `Red. Status` / `Aum. Status` / `Subir NV` | — |
| Poison / Paralysis / Sleep | Veneno / Paralisia / Sono | — |
| Confusion / Blind / Silence (Mute) | Confusão / Cegueira / Silêncio (Silenciar) | — |
| Curse / Egghead / Hex | Maldição / Cabeça-Oca / Feitiço *(or `Hex` if proper term)* | — |

### C. World, Lore, Faerie Colony & Chapter Titles

| English | PT-BR Standard | Notes |
| :--- | :--- | :--- |
| Dragon / Dragons / Wind Dragon | Dragão / Dragões / Dragão do Vento | Keep Dragon form names EN |
| Endless | Eternos (singular: Eterno) | Ancient god-beings (`Fou-Lu`, `Ryu`, etc.) |
| Hex | Hex *(or Maldição / Poder Hex)* | Use **Hex** when referring to the Imperial weapon/energy; **Maldição** for the status effect (`Curse`) |
| Carronade | Carronada | The Imperial Hex cannon weapon |
| Sandflier | Veleiro de Areia (ou Areieiro) | Prefer **Veleiro de Areia** (clear & natural) |
| Faerie / Faerie Colony (Village) | Fada / Colônia das Fadas | Keep job titles short in `INIT.DAT[6]`: `Caçar`, `Arar`, `Cultivar`, `Itens`, `Armas`, `Estalagem`, `Buscar`, `Tropas`, `Música`, `Arte`, `Aurum`, `Jogos`, `Títulos` |
| Manillo / Manillo Shop | Manillo / Loja Manillo | Fish-merchant clan |
| Dragon Eye / Dragon Tear | Olho do Dragão / Lágrima do Dragão | — |
| First Emperor | Primeiro Imperador | — |

#### Canonical Chapter Titles (`START.DAT` slots `55..68`)
- `1-Signs & Portents` → `1-Sinais e Presságios`
- `2-Associations` → `2-Associações`
- `3-Missing Princess` → `3-A Princesa Desaparecida`
- `4-The Broken Sword` → `4-A Espada Quebrada`
- `5-The Wind Dragon` → `5-O Dragão do Vento`
- `6-Mysteries` → `6-Mistérios`
- `7-Prophecy` → `7-Profecia`
- `8-Awakenings` → `8-Despertares`
- `9-Fools and Men` → `9-Tolos e Homens`
- `10-Levant` → `10-Levante`
- `11-The Path Ahead` → `11-O Caminho à Frente`
- `12-Journey's End` → `12-Fim da Jornada`
- `13-Of Gods and Men` → `13-De Deuses e Homens`

---

## 3. Character Voice & Register Guidelines

Preserve each character's distinct personality in natural Brazilian Portuguese:

- **`Ershin` (`{CHAR:05}`):** Always refers to itself in the **3rd person** using `{CHAR:05}` instead of `"eu"` (e.g., `"{CHAR:05} concorda."`, `"Não podem escapar de {CHAR:05} tão facilmente."`). Mechanical, literal, slightly formal/robotic cadence (`"Afirmativo."`, `"Perdão."`, `"Analisando..."`).
- **`Scias` (`{CHAR:03}`):** Quiet, laconic, hesitant. Match English stutters and pauses naturally with `...` and hyphenated starts (`"S-sim..."`, `"E-eu... acho que sim..."`, `"É... verdade."`).
- **`Fou-Lu` (`{CHAR:06}`):** Imperial, solemn, ancient, and haughty. English uses archaic `"thou / thy / dost"`. Render in dignified, formal/archaic PT-BR using **`vós`** (or elevated regal register consistently across all Fou-Lu scenes: e.g., `"Vós desejais legar-lhes um futuro, não é verdade?"`, `"Podeis suportar o meu poder?"`, `"Mortais insolentes..."`).
- **`Manillo` merchants:** Playful, cheerful fish-obsessed merchants (English uses comical `"zee"` / `"'ave"` French-style accent). Render with warm, exuberant merchant flair and light playful cadence in PT-BR (e.g., `"Ah, o mar azul, os peixes fresquinhos e os Manillo! Não se vive sem eles, meu amigo!"`) — keep spelling clean and readable without broken ASCII/unmapped chars.
- **`Nina` (`{CHAR:01}`):** Warm, earnest, polite, compassionate young princess (`você`, expressive punctuation, sincere tone).
- **`Cray` (`{CHAR:02}`):** Stoic, honorable tribal chief; direct, grounded, protective, economical with words.
- **`Ursula` (`{CHAR:04}`):** Imperial military officer; crisp, confident, disciplined, direct, occasionally sharp.
- **`Ryu` (`{CHAR:00}`):** Quiet protagonist; keep rare battle shouts/prompts short and determined.
- **Generic NPCs / Villagers / Soldiers:** Natural, idiomatic Brazilian Portuguese matching their social register (casual/colloquial for villagers & kids, formal/respectful for elders & nobles, brisk for soldiers). Avoid literal English calques ("você está bem?" instead of awkward word-for-word phrasing).

---

## 4. Mandatory Technical Encoding & Validation Rules

Every Phase 2 translator **MUST** obey all 7 technical rules without exception:

1. **Allowed Characters ONLY:**
   - Standard printable ASCII (`A-Z`, `a-z`, `0-9`, space, `! " # % & ' ( ) * + , - . / : ; = ? [ \ ]`).
   - **Native PT-BR accented glyphs (`0x88..0xA1`):**
     `á à â ã é ê í ó ô õ ú ç Á À Â Ã É Ê Í Ó Ô Õ Ú Ç º ª`
   - **FORBIDDEN characters (will fail `validate.py`):** smart/curly quotes (`“ ” ‘ ’`), em/en-dash (`— –`, use `--` or `-`), Unicode ellipsis (`…`, use `...`), umlaut (`ü`), Spanish `ñ`/`¡`/`¿`, raw `$`, `<`, `>`, `@`, `^`, `_`, `` ` ``, `|`, stray `{` or `}`.
   - Use explicit tags for special font glyphs: `{ZENNY}` (`Z`), `{IV}` (`IV`), `{STAR}` (`★`), `{DEG}` (`°`), `{GT}` (`>`), `{WAVE}` (`~`), `{MDOT}` (`・`), `{DOT2}`, `{LQ}`, `{RQ}`, `{BTN_0}`..`{BTN_9}`.

2. **Exact Control-Tag Preservation:**
   - Copy **every** `{TAG}` from `"en"` verbatim into `"ptbr"` with identical hex bytes!
   - **Exact order required:** `{WIN:XX}`, `{PORTRAIT:A0:A1}`, `{GOTO:LO:HI}`, `{SUBMSG:LO:HI}`, `{CHOICE:OO:FF}`, `{CHOICE_RAW:OO}`, `{SFX:XX}`, `{WAIT:XX}`, `{PAUSE}`, `{SPEED:XX}`, `{/SPEED}`, `{FX_ON}`, `{FX_OFF}`, `{FX:XX}`, `{PAGE}`.
   - **Exact multiset required (may reorder for PT-BR grammar):** `{CHAR:XX}`, `{LEADER}`, `{VAR:XX}`, `{CAT:SS:II}`, `{BTN_0..9}`, `{COLOR:XX}`, `{/COLOR}` (always keep `{COLOR:XX}...{/COLOR}` balanced!).
   - **NEVER** drop or alter portrait tags (`{PORTRAIT:C2:40}` must stay `{PORTRAIT:C2:40}` byte-exact!).

3. **Choice Box Rules (`{CHOICE:OO:FF}` / `{CHOICE_RAW:OO}`):**
   - `\n` (`0x01`) separates **selectable menu options** — you **MUST** keep the exact same number of `\n`-separated options as `"en"`!
   - `{NL2}` (`0x08`) is a **visual continuation wrap inside one option** — **NEVER** replace `{NL2}` with `\n`! You may unwrap `{NL2}` if the PT-BR option fits on 1 line (`<= 140px`), or insert `{NL2}` to wrap a long PT-BR option onto 2 visual lines without adding a selectable option.

4. **VWF Pixel Width & Line Budgets (320×240 logical px):**
   - Every entry carries its exact `context`, `max_px`, and `max_lines` (and `preserve_line_count` when UI-critical).
   - Reference budgets:
     - `dialogue_1p` (1 portrait): **≤ 148 px** (~20–22 chars), **≤ 3 lines/page**
     - `dialogue_2p` (2 portraits): **≤ 104 px** (~15 chars), **≤ 3 lines/page**
     - `dialogue_0p` (no portrait): **≤ 195 px** (~27–30 chars), **≤ 3 lines/page**
     - `choice`: **≤ 140 px** (~20 chars) per visual line
     - `battle_1p`: **≤ 145 px**, **≤ 3 lines/page** | `battle_sys`: **≤ 232 px**
     - `desc` (descriptions): **≤ 256 px**, **≤ 2 lines**
     - `menu`: **≤ 228 px** (preserve exact line count when `preserve_line_count: true`)
   - Use `bof4_ptbr.codec.measure_line_px(line)` and `bof4_ptbr.codec.wrap_dialogue_text(text, max_px, auto_paginate=False)` to wrap cleanly so every line passes VWF checks without awkward orphans!

5. **Page Count (`{PAGE}`):**
   - Keep the exact same `{PAGE}` count as `"en"` (do not invent extra `{PAGE}` breaks unless an entry explicitly sets `"allow_page_split": true`). Write concise, punchy PT-BR so every page fits cleanly within `max_lines` and `max_px`.

6. **Locked Entries & Stubs:**
   - If `"locked": true`, leave `"ptbr"` untouched (`""` or identical to `"en"`).
   - Never touch entries containing `{RAW:...}` or `{KANJI:...}` (legacy unused JP stubs).

7. **Mandatory Validation Gate Before Completion:**
   - Before handing off your shard, run:
     ```bash
     python3 -m bof4_ptbr.validate bof4_ptbr/corpus/<your_shard>.json
     ```
   - Exit code **MUST be `0` (0 errors, 0 warnings)**! Do not post completion until validation is 100% green.
