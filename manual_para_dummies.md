# navis-mcp: manual para dummies

Guía corta, sin tecnicismos, para instalar navis-mcp y probarlo. Estado actual: **v0.1**. Funciona con archivos exportados y con un Navisworks simulado. La conexión con un Navisworks real todavía no está lista (el add-in está sin compilar), así que hoy no puede leer ni modificar tu modelo abierto.

## 1. Qué es, en una frase

Un puente entre un asistente de IA (Claude, por ejemplo) y los resultados de clash detection de Navisworks. La IA no recibe miles de filas crudas: recibe una lista de problemas ordenada por prioridad, con la razón de cada uno, quién debe moverse y qué falta por revisar.

## 2. Instalación (una sola vez)

Necesitas Python 3.11 o superior. Abre PowerShell en la carpeta del proyecto y crea un entorno propio:

```powershell
cd D:\IA_WORK\MCP_NAVIS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**Importante:** usa siempre el entorno `.venv`. Si instalas sin él, pip mete las dependencias en el Python general y puede dañar otros programas. Pasó una vez: `mcp` trae versiones nuevas de `starlette` y `websockets`, y otros paquetes del equipo (por ejemplo `gradio` o `fastapi`) piden versiones más viejas. El aviso "dependency conflicts" dice exactamente eso. No afecta a navis-mcp, solo a esas otras aplicaciones. Si alguna se rompió, ejecuta fuera del entorno `.venv`:

```powershell
pip install "starlette<0.49" "websockets<12"
```

Con eso `fastapi` y `gradio` deberían volver a la normalidad (no lo pude comprobar en tu equipo). Desde ese momento navis-mcp se usa solo dentro de `.venv`.

Cada vez que abras una terminal nueva, activa el entorno otra vez: `.\.venv\Scripts\Activate.ps1`.

## 3. La prueba más fácil: el recorrido guiado

```powershell
navis-mcp-cli demo
```

En unos segundos recorre todo el flujo contra un Navisworks falso: estado, análisis, plan de cambios, ejecución y verificación. No necesita nada más ni toca tus datos. Para verlo en inglés: `navis-mcp-cli demo --lang en`.

Otros comandos útiles:

| Comando | Qué hace |
|---|---|
| `navis-mcp-cli tools` | Lista las 14 herramientas |
| `navis-mcp-cli call nw_status` | Llama una herramienta suelta |
| `navis-mcp-cli sample examples\torre.json` | Crea un archivo de ejemplo (una torre de 5 niveles) |
| `navis-mcp-cli analyze examples\torre.json --lang es` | Analiza un archivo y escribe el informe |

## 4. Por qué `navis-mcp` y `navis-mcp-cli simulate` parecen congelados

No lo están. Son programas que **esperan**:

- `navis-mcp` es el servidor. No se maneja a mano: lo arranca un asistente (Claude Desktop o Claude Code) y se comunica con él por debajo. Si lo abres en una terminal, ahora muestra una nota y se cierra.
- `navis-mcp-cli simulate` es el Navisworks falso. Se queda esperando conexiones hasta que pulses `Ctrl+C`. Solo hace falta si quieres que un asistente lo use.

## 5. Conectar un asistente

### Claude Desktop

La forma segura, con el entorno `.venv` activo:

```powershell
navis-mcp-cli desktop-config --write
```

Hace una copia de respaldo del archivo, agrega `navis-mcp` sin tocar tus otros servidores y se niega a escribir si el archivo ya está dañado. Después cierra Claude Desktop por completo (también en la bandeja del sistema) y ábrelo otra vez. Sin `--write` solo muestra la entrada que habría que agregar.

A mano: abre `%APPDATA%\Claude\claude_desktop_config.json`. Si el archivo ya tiene `"mcpServers"`, **no pegues el bloque completo**: agrega solo la entrada `"navis-mcp": {...}` dentro de ese objeto, con una coma después de la entrada anterior. Pegar un bloque nuevo después de la última llave `}` deja el archivo inválido y Claude Desktop no arranca ("Unexpected non-whitespace character after JSON"). El bloque completo, solo para un archivo vacío (ajusta la ruta si tu carpeta es otra):

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

Cierra Claude Desktop por completo y ábrelo otra vez. Aparecerán las herramientas `nw_*`.

### Claude Code

```powershell
claude mcp add navis-mcp -- D:\IA_WORK\MCP_NAVIS\.venv\Scripts\navis-mcp.exe
```

### Con el Navisworks falso

Deja una terminal abierta con `navis-mcp-cli simulate` y conecta el asistente como arriba. Lo encuentra solo.

## 6. Qué pedirle al asistente

- "Revisa el estado de Navisworks."
- "Analiza el archivo `D:\...\clash.xml` y dime los cinco problemas más graves."
- "¿Qué disciplinas no tienen resultados? ¿Qué pruebas nunca se ejecutaron?"
- "Dame el detalle del problema NW-9504F9."
- "Genera un informe en CSV y otro en BCF."
- "Agrupa los 20 problemas más graves." (primero muestra un plan; no cambia nada hasta que lo confirmes)

Para analizar tus propios clashes sin Navisworks conectado: en Navisworks, Clash Detective, pestaña Report, formato XML, y pásale la ruta del archivo al asistente. Los CSV y los JSON de navis-mcp también sirven. Los exportes reales varían entre versiones; si uno falla, guárdalo y avisa, es información útil para mejorar el lector.

## 7. Seguridad: lo que conviene saber

- `NAVIS_MCP_READ_ONLY=1` bloquea toda escritura en Navisworks. Déjalo así mientras pruebas.
- Los informes se guardan solo en `%USERPROFILE%\.navis_mcp\exports`, salvo que definas `NAVIS_MCP_OUTPUT_ROOTS`.
- Cambiar algo en Navisworks siempre son dos pasos: un plan (que no modifica nada) y su ejecución por `plan_id`.

## 8. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `navis-mcp` no se reconoce como comando | Activa el entorno: `.\.venv\Scripts\Activate.ps1` |
| El asistente no ve las herramientas | Revisa la ruta del `.exe` en la configuración y reinicia el asistente por completo |
| "no Navisworks instance" | Normal sin Navisworks: usa un archivo (`path=`) o abre `simulate` |
| Un XML no se lee | Prueba con CSV o avisa del caso |
| Los resultados dicen "nunca ejecutada" | Esa prueba no se corrió en Navisworks: ausencia de clashes no significa que esté limpio |

## 9. Qué no hace todavía

Leer ni modificar un Navisworks real abierto, crear viewpoints, colorear el modelo ni generar PDF. Ver [docs/ROADMAP.md](docs/ROADMAP.md).
