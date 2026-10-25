---
name: categorizar-gastos-banco
description: Categoriza un extracto bancario (CSV de BBVA, Kutxabank, Revolut, B100 o cualquier otro banco) contra el histórico real de gastos de la usuaria y genera un Excel de revisión con las filas nuevas resaltadas donde hace falta confirmar categoría y reparto antes de pegarlas en su Google Sheet maestro. Actívala SIEMPRE que la usuaria mencione: importar o categorizar un extracto bancario, movimientos del banco, un csv del banco, "categorizar mis gastos", BBVA, Kutxabank, Revolut, B100, subir/procesar un extracto, o pedir ayuda para meter transacciones nuevas en su hoja de gastos personal — incluso si no dice la palabra "categorizar" explícitamente.
---

# Categorizar gastos del banco

La usuaria lleva sus gastos compartidos con su pareja (Marin) en un Google
Sheet manual — cada fila la escribe a mano. Esta skill le ahorra la parte
mecánica: coge un extracto bancario en bruto y le devuelve casi-listas las
filas nuevas, categorizadas por precedente y marcadas en color donde su
criterio humano sigue haciendo falta. Ella sigue teniendo el control final
— nada se escribe en el Google Sheet real, solo se genera un Excel de
staging para que lo revise y luego pegue las filas ya correctas.

## Antes de empezar

Necesitas tres cosas de la usuaria (pregunta si falta alguna — no asumas
ninguna, ella prefiere decirlas explícitamente a que las adivines):

1. **La ruta del CSV del extracto bancario.**
2. **Desde qué fecha necesita los datos.** Ella conoce mejor que nadie hasta
   dónde llega su Google Sheet — pregúntaselo siempre, en vez de derivarlo
   tú sola del histórico o de la última ejecución. Esta fecha es la que manda
   en el Paso 0; el fichero de control ahí es solo un cruce de seguridad, no
   la fuente de verdad.
3. **De qué cuenta es.** Cada cuenta tiene un identificador corto y consistente
   (usa siempre el mismo texto para la misma cuenta real, ej. `revolut-viboras`,
   `revolut-conjunta`, `bbva-viboras`, `kutxabank-viboras`) — lo necesitas para
   el control de duplicados del Paso 0. Según la cuenta, los valores de reparto
   cambian:

   | Cuenta | Paid by | Common | Quien se beneficia |
   | --- | --- | --- | --- |
   | Cuenta personal de Viboras (Revolut/BBVA/Kutxabank a su nombre) | `Viboras` | inferir por precedente (Paso 2) | inferir por precedente (Paso 2) |
   | Cuenta conjunta con Marin | `Cuenta conjunta` | **siempre `Sí`** | **siempre `Marin;Viboras`** |
   | Cuenta personal de Marin | `Marin` | inferir por precedente | inferir por precedente |

   Para la cuenta conjunta no hay nada que adivinar en esos tres campos —
   si la usuaria dice que ahí los gastos son siempre a medias, son fijos.
   Solo Category y Subcategory siguen necesitando inferencia (Paso 2-3), igual
   que en cualquier otra cuenta.

## Paso 0 — Cruza la fecha que te dio con el control de importaciones

El corte real es **la fecha que la usuaria te dio en "Antes de empezar"**:
procesa solo transacciones estrictamente posteriores a ella. No la sustituyas
por nada de lo que sigue — lo de aquí es solo para avisarla si algo no
cuadra con lo que la skill recuerda, nunca para pisar su respuesta.

`skills-data/ultimas-importaciones.json` guarda, por cuenta, la fecha hasta
la que llegó la última tanda que le generaste:

```json
{
  "revolut-viboras": {
    "last_reviewed_through": "2026-09-03"
  }
}
```

Antes de procesar, compara la fecha que ella dio con `last_reviewed_through`
de esa cuenta (si la cuenta no aparece todavía, no hay nada que cruzar, sigue
sin más):

- Si su fecha es **posterior** a `last_reviewed_through`: normal, hay un
  hueco esperado (tiempo que pasó desde la última vez). Sigue sin más.
- Si su fecha es **igual o anterior**: probablemente esa tanda ya se la
  generaste antes y quizás nunca la pegó en su Sheet (o la pegó y te está
  pidiendo repetir un rango ya cubierto). Dile lo que recuerdas — *"la última
  vez te generé `<cuenta>` hasta `<last_reviewed_through>`, ¿quieres que
  incluya igualmente ese rango o prefieres que empiece después?"* — y sigue
  con lo que ella decida. Es su Sheet, ella manda.

Al terminar de generar el Excel de revisión (Paso 4), actualiza
`last_reviewed_through` de esa cuenta a la fecha más reciente de las
transacciones procesadas, y guarda el JSON — así la próxima vez tienes algo
con qué cruzar.

## Paso 1 — Lee el extracto bancario

Cada banco exporta un CSV distinto — no hay un parser fijo por banco, así
que inspecciona la cabecera y unas cuantas filas de muestra para identificar:

- La columna de fecha, y en qué formato viene (puede no ser DD/MM/YYYY).
- La columna de importe, y su convención de signo. Algunos bancos ya usan
  negativo para gastos (como el histórico); otros usan columnas separadas de
  cargo/abono, o siempre positivo con un tipo de movimiento aparte. Normaliza
  todo a la convención del histórico: negativo = Gasto, positivo = Ingreso.
- La columna de concepto/descripción — normalmente viene con ruido (IDs de
  referencia, "COMPRA TARJETA 1234 EN...", fechas de valor). Vas a limpiarla
  en el paso 3, no la copies tal cual.
- Ignora cualquier categoría que el propio banco asigne — no es fiable ni
  compatible con el vocabulario de la usuaria.

Si una fila no parece un movimiento real (saldo inicial, cabecera repetida,
fila vacía), descártala. Descarta también los movimientos pendientes/no
liquidados (columnas tipo "estado" o "state" con valores como `PENDIENTE`) —
espera a que el propio extracto los liquide en una próxima importación.

**Descarta los movimientos que no son un gasto o ingreso real, solo
dinero cambiando de sitio entre cuentas de la propia usuaria/pareja:**

- Recargas o ingresos del monedero desde una tarjeta o cuenta propia (ej.
  "Una recarga de Apple Pay con...") — es fondear la cuenta, no gastar.
- Transferencias hacia o desde otra cuenta que la usuaria también controla
  (su cuenta conjunta, una cuenta de Marin) — si esa cuenta se importa por
  su lado, contar la transferencia aquí Y el gasto real allí sería duplicar.
  Reconoce estas por el nombre del titular en la descripción, no asumas que
  toda "Transferencia" es de este tipo — una transferencia a un tercero
  (otra persona, un comercio) sí es un gasto real y se procesa normal.

Si dudas si un movimiento es interno o real, pregunta en vez de asumir — es
mejor una pregunta que un gasto fantasma o uno que desaparece.

## Paso 2 — Aprende del histórico

Lee `skills-data/historico-gastos.csv` (en la raíz del repo, junto a este
proyecto). Son ~1.622 transacciones reales que la usuaria ya categorizó a
mano entre enero de 2025 y julio de 2026 — es tu única fuente de verdad para
tres cosas, todas por precedente de comercio/concepto:

- **Category**: vocabulario cerrado. Usa solo una de las categorías que ya
  aparecen en el histórico (Compra, Ocio gastronómico, Casa, Transporte,
  Regalo, Viaje, Ropa, Health, Deporte, Nomina, Bizum, Suscripciones,
  Proyectos, Compra Casa, Cultura, Gato, Donacion). No inventes categorías
  nuevas aunque el concepto no encaje perfectamente — elige la más cercana.
- **Common** (Sí/No) y **Quien se beneficia** (Marin / Viboras /
  Marin;Viboras): mira cómo se marcó ese mismo comercio o tipo de gasto en el
  pasado. Un supermercado que casi siempre fue "Sí, Marin;Viboras" es buena
  señal de que la próxima compra ahí también lo es — pero es una sugerencia,
  no un hecho, así que siempre queda marcada para revisión (ver Paso 4).

Un mismo comercio puede aparecer con grafías distintas ("Carrefour",
"Carrefour Exprés", "Carrefour caja estanteria") — usa criterio, no
coincidencia exacta de texto, para relacionar el concepto del extracto con
el precedente más parecido.

## Paso 3 — Construye cada fila nueva

Para cada transacción del extracto, rellena exactamente estas columnas
(son las únicas de entrada — el resto se explica en la nota del final):

| Columna | Cómo rellenarla |
| --- | --- |
| `Year` | Año de la fecha, ej `"2026"` |
| `Month` | Mes en español, minúscula, ej `"septiembre"` |
| `Date` | `DD/MM/YYYY`, igual que el histórico |
| `Paid by` | Según la tabla de cuentas de "Antes de empezar" — fijo por la cuenta que se está importando |
| `Income/expense` | `Gasto` si el importe es negativo, `Ingreso` si es positivo. Usa `Inversion` solo si el concepto lo deja claro (ej. una transferencia a un bróker) |
| `Amount` | Formato europeo, coma decimal, con signo — ej `"-24,11"` (igual que el histórico, no uses punto) |
| `Category` | Del vocabulario cerrado, por precedente (Paso 2) |
| `Subcategory` | Descripción limpia del comercio/motivo, en el mismo estilo que el histórico (ej. `"Mercadona"`, no `"COMPRA TARJETA 4521 MERCADONA 28941"`) |
| `Common` | `Sí` / `No` — fijo (`Sí`) si es la cuenta conjunta; si no, mejor suposición por precedente |
| `Quien se beneficia` | `Marin` / `Viboras` / `Marin;Viboras` — fijo (`Marin;Viboras`) si es la cuenta conjunta; si no, mejor suposición por precedente |

Para cada fila, decide también:

- **`guess_fields`**: en una cuenta personal, siempre
  `["Category", "Common", "Quien se beneficia"]` — son inferencias tuyas,
  nunca las trates como definitivas. En la cuenta conjunta, `Common` y
  `Quien se beneficia` son valores fijos (no una suposición) así que
  **no** los incluyas aquí — solo `["Category"]`.
- **`low_confidence_fields`**: incluye `"Category"` aquí (además de en
  `guess_fields`) cuando el concepto no tenga un precedente claro en el
  histórico — comercio nuevo, concepto ambiguo, o vocabulario que podría
  encajar en dos categorías distintas. Sé honesta con la confianza real, no
  optimista: es mejor que ella revise algo que ya estaba bien que se le
  cuele algo mal categorizado sin aviso.

Si al revisar un movimiento raro (un Bizum enorme, una transferencia sin
comercio claro, etc.) le preguntas a la usuaria qué es y ella te lo confirma
explícitamente, esa Category ya no es una suposición tuya — es un hecho que
te dio ella. No la metas en `guess_fields` ni en `low_confidence_fields`: solo
`Common` y `Quien se beneficia` siguen siendo inferencia (a menos que también
te los haya confirmado ella misma, en cuyo caso tampoco van ahí).

## Paso 4 — Genera el Excel de revisión

No escribas el `.xlsx` a mano. Escribe un JSON temporal con esta forma:

```json
{
  "output_path": "/Users/cristinaviborascaballero/gastos/revisiones/gastos_revision_<fecha-de-hoy>.xlsx",
  "rows": [
    {
      "Year": "2026", "Month": "septiembre", "Date": "03/09/2026",
      "Paid by": "Viboras", "Income/expense": "Gasto", "Amount": "-24,11",
      "Category": "Compra", "Subcategory": "Mercadona",
      "Common": "Sí", "Quien se beneficia": "Marin;Viboras",
      "guess_fields": ["Category", "Common", "Quien se beneficia"],
      "low_confidence_fields": []
    }
  ]
}
```

y ejecútalo con:

```bash
python3 .claude/skills/categorizar-gastos-banco/scripts/generate_xlsx.py <ruta-al-json-temporal>
```

El script coloca las columnas en el mismo orden que
`skills-data/historico-gastos.csv`, resalta en amarillo las celdas marcadas
en `guess_fields` y en naranja las de `low_confidence_fields`, y deja en
blanco las columnas que no rellenaste (`Marin disfruta`, `Viboras disfruta`,
`Pagado por Marin`, `Pagado por Viboras`, `Saldo Marin`, `Saldo Viboras` y
las columnas de coeficientes) — son casi con toda seguridad fórmulas en la
hoja real que se recalculan solas a partir de `Amount`, `Paid by`, `Common`
y `Quien se beneficia`, así que escribir un número fijo ahí se quedaría
desactualizado en cuanto la usuaria corrija algo en la revisión.

## Paso 5 — Resume el resultado

El script imprime cuántas filas escribió y cuántas quedaron en baja
confianza — usa esos números tal cual, no los inventes. Dile:

- Que abra el Excel generado y revise sobre todo las celdas en amarillo y
  naranja (categoría, común, quién se beneficia).
- Que cuando haya terminado la revisión, avise y le envías las filas
  directamente al Google Sheet (Paso 6).

## Paso 6 — Envía las filas al Google Sheet

Cuando la usuaria confirme que ha terminado de revisar el Excel, ejecuta:

```bash
python3 -I .claude/skills/categorizar-gastos-banco/scripts/send_to_sheets.py \
  <ruta-al-xlsx-revisado> \
  <script_url>
```

La `script_url` es la URL de despliegue del Apps Script (la misma que usa
la webapp para leer). Si la usuaria no la tiene a mano, pídesela — está en
el Google Apps Script bajo "Implementaciones".

El script lee las columnas `Date`, `Paid by`, `Income/expense`, `Amount`,
`Category`, `Subcategory`, `Common` y `Quien se beneficia` del Excel y las
envía en una petición POST al endpoint `action=write_batch`. El Apps Script
las añade al final de la hoja.

Si el script devuelve OK, confirma cuántas filas se escribieron. Si devuelve
error, muestra el mensaje completo para que la usuaria pueda diagnosticarlo.
