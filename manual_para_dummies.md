# navis-mcp: manual para dummies

Guía paso a paso para instalar navis-mcp y probarlo. Cada paso dice **dónde** se escribe (qué terminal) y **qué debes ver**.

Estado actual: **v0.1**. Funciona con archivos exportados y con un Navisworks simulado. La conexión con un Navisworks real todavía no está lista (el add-in está sin compilar), así que hoy no puede leer ni modificar tu modelo abierto.

## 0. Cómo abrir una terminal lista para trabajar

Este procedimiento se repite **cada vez que abras una terminal nueva**. Cada terminal es independiente: la que tiene el entorno activo no comparte nada con otra.

1. Menú Inicio, escribe `PowerShell`, Enter.
2. Escribe y pulsa Enter:
   ```powershell
   cd D:\IA_WORK\MCP_NAVIS
   ```
3. Activa el entorno:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   **Debes ver** que la línea empieza con `(.venv)`. Si no aparece, los comandos `navis-mcp...` no funcionarán o usarán el Python general.

Si el paso 3 dice que la ejecución de scripts está deshabilitada, escribe una sola vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, responde `S` y repite el paso 3.

## 1. Qué es, en una frase

Un puente entre un asistente de IA (Claude, por ejemplo) y los resultados de clash detection de Navisworks. La IA no recibe miles de filas crudas: recibe una lista de problemas ordenada por prioridad, con la razón de cada uno, quién debe moverse y qué falta por revisar.

## 2. Instalación (una sola vez)

Necesitas Python 3.11 o superior. Con una terminal abierta en la carpeta del proyecto (pasos 1 y 2 de la sección 0, todavía sin entorno):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**Debes ver** `(.venv)` al inicio de la línea y, al final, `Successfully installed ... navis-mcp-0.1.0`.

**Por qué siempre `.venv`:** sin él, pip mete las dependencias en el Python general y puede dañar otros programas. Pasó una vez: `mcp` trae versiones nuevas de `starlette` y `websockets`, y otros paquetes del equipo (por ejemplo `gradio` o `fastapi`) piden versiones más viejas. El aviso "dependency conflicts" dice exactamente eso. No afecta a navis-mcp, solo a esas otras aplicaciones. Si alguna se rompió, abre una terminal **sin** entorno activo (sin `(.venv)`) y ejecuta:

```powershell
pip install "starlette<0.49" "websockets<12"
```

Con eso `fastapi` y `gradio` deberían volver a la normalidad (no se comprobó en tu equipo).

## 3. Actualizar a la última versión

Cuando se publique una mejora, en una terminal preparada (sección 0):

```powershell
git pull origin main
git log --oneline -1
```

La segunda línea muestra el commit en el que quedaste. No hace falta reinstalar: el entorno apunta directamente a la carpeta. Se escribe `git pull origin main` completo, porque `git pull` a secas no sabe de dónde bajar.

## 4. La prueba más fácil: el recorrido guiado

En una terminal preparada (sección 0):

```powershell
navis-mcp-cli demo
```

En unos segundos recorre todo el flujo contra un Navisworks falso: estado, análisis, plan de cambios, ejecución y verificación. **Debes ver** cinco pasos numerados y al final "Listo.". No necesita nada más ni toca tus datos. En inglés: `navis-mcp-cli demo --lang en`.

Otros comandos, en la misma terminal:

| Comando | Qué hace |
|---|---|
| `navis-mcp-cli tools` | Lista las 14 herramientas |
| `navis-mcp-cli call nw_status` | Llama una herramienta suelta |
| `navis-mcp-cli sample examples\torre.json` | Crea un archivo de ejemplo (una torre de 5 niveles) |
| `navis-mcp-cli analyze examples\torre.json --lang es` | Analiza un archivo y escribe el informe |

## 5. Por qué `navis-mcp` y `navis-mcp-cli simulate` parecen congelados

No lo están. Son programas que **esperan**:

- `navis-mcp` es el servidor. No se maneja a mano: lo arranca el asistente (Claude Desktop o Claude Code) y se comunica con él por debajo. Si lo escribes en una terminal, muestra una nota y se cierra.
- `navis-mcp-cli simulate` es el Navisworks falso. Se queda esperando hasta que pulses `Ctrl+C`. Solo hace falta si quieres que un asistente lo use, y **necesita su propia terminal abierta** mientras lo uses.

## 6. Conectar Claude Desktop, paso a paso

### 6.1 Registrar navis-mcp en Claude Desktop (una sola vez)

1. Abre una terminal preparada (sección 0).
2. Escribe:
   ```powershell
   navis-mcp-cli desktop-config --write
   ```
   **Debes ver** `backup: ...` y `navis-mcp added to ...claude_desktop_config.json`. El comando guarda una copia de respaldo del archivo y no toca tus otros servidores.
3. Si en cambio dice `is not valid JSON (line N ...)`, el archivo de configuración tiene un error previo y **no se escribió nada**. Corrígelo: cierra Claude Desktop, escribe `notepad "$env:APPDATA\Claude\claude_desktop_config.json"`, ve a la línea indicada con `Ctrl+G`, corrige o borra el texto sobrante, guarda y repite el paso 2.
4. Cierra Claude Desktop **por completo**: haz clic en la flecha `^` junto al reloj de Windows, clic derecho en el icono de Claude, Salir. Cerrar solo la ventana no basta.
5. Abre Claude Desktop de nuevo.

### 6.2 Usarlo con el Navisworks falso (cada vez)

1. Abre una terminal preparada (sección 0) y escribe:
   ```powershell
   navis-mcp-cli simulate
   ```
   **Debes ver** `Navisworks simulator listening on tcp://127.0.0.1:...`. **Deja esa terminal abierta**, sin escribir nada más en ella.
2. En Claude Desktop abre un chat nuevo. Pide: "Revisa el estado de Navisworks y analiza los problemas más graves".
3. La primera vez Claude pedirá permiso para usar la herramienta: acepta. **Debes ver** 35 problemas, uno crítico.
4. Al terminar, vuelve a la terminal del simulador y pulsa `Ctrl+C`.

### Registrar a mano (solo si no puedes usar el comando)

Abre `%APPDATA%\Claude\claude_desktop_config.json`. Si ya tiene `"mcpServers"`, **no pegues el bloque completo**: agrega solo la entrada `"navis-mcp": {...}` dentro de ese objeto, con una coma después de la entrada anterior. Pegar un bloque nuevo después de la última llave `}` deja el archivo inválido y Claude Desktop no arranca ("Unexpected non-whitespace character after JSON"). El bloque completo, solo para un archivo vacío:

```json
{
  "mcpServers": {
    "navis-mcp": {
      "command": "D:\\IA_WORK\\MCP_NAVIS\\.venv\\Scripts\\navis-mcp.exe",
      "env": { "NAVIS_MCP_READ_ONLY": "1" }
    }
  }
}
```

### Claude Code

En una terminal preparada (sección 0):

```powershell
claude mcp add navis-mcp -- D:\IA_WORK\MCP_NAVIS\.venv\Scripts\navis-mcp.exe
```

## 7. Qué pedirle al asistente

- "Revisa el estado de Navisworks."
- "Analiza el archivo `D:\...\clash.xml` y dime los cinco problemas más graves."
- "¿Qué disciplinas no tienen resultados? ¿Qué pruebas nunca se ejecutaron?"
- "Dame el detalle del problema NW-9504F9."
- "Genera un informe en CSV y otro en BCF."
- "Agrupa los 20 problemas más graves." (primero muestra un plan; no cambia nada hasta que lo confirmes)

Para analizar tus propios clashes sin Navisworks conectado: en Navisworks, Clash Detective, pestaña Report, formato XML, y pásale la ruta del archivo al asistente. Los CSV y los JSON de navis-mcp también sirven. Los exportes reales varían entre versiones; si uno falla, guárdalo y avisa, es información útil para mejorar el lector.

## 8. Seguridad: lo que conviene saber

- `NAVIS_MCP_READ_ONLY=1` bloquea toda escritura en Navisworks. `desktop-config` lo deja activado; si quieres permitir escrituras, vuelve a ejecutar el comando con `--allow-writes`.
- Los informes se guardan solo en `%USERPROFILE%\.navis_mcp\exports`, salvo que definas `NAVIS_MCP_OUTPUT_ROOTS`.
- Cambiar algo en Navisworks siempre son dos pasos: un plan (que no modifica nada) y su ejecución por `plan_id`.

## 9. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `navis-mcp-cli` no se reconoce como comando | La terminal no tiene el entorno: repite la sección 0 |
| `invalid choice: '...'` al escribir un comando del manual | Tu copia está desactualizada: sección 3 |
| `desktop-config` dice que el archivo no es JSON válido | Paso 3 de la sección 6.1 |
| Claude Desktop no muestra las herramientas | Ciérralo por completo (paso 4 de 6.1) y ábrelo otra vez |
| "no Navisworks instance" | Normal sin Navisworks: usa un archivo o deja `simulate` abierto en otra terminal |
| Un XML no se lee | Prueba con CSV o avisa del caso |
| Los resultados dicen "nunca ejecutada" | Esa prueba no se corrió en Navisworks: ausencia de clashes no significa que esté limpio |

## 10. Qué no hace todavía

Leer ni modificar un Navisworks real abierto, crear viewpoints, colorear el modelo ni generar PDF. Ver [docs/ROADMAP.md](docs/ROADMAP.md).
