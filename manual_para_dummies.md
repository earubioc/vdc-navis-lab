# vdc-navis-lab: manual para dummies

Guía paso a paso para instalar vdc-navis-lab y probarlo. Cada paso dice **dónde** se escribe (qué terminal) y **qué debes ver**.

Estado actual: **v0.2**. Funciona con archivos exportados, con un Navisworks simulado y con Navisworks Manage 2026 real: lee pruebas de Clash Detective, las analiza, y escribe de vuelta (agrupar, estado, guardar) verificado releyendo el documento (ver la sección 10).

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
   **Debes ver** que la línea empieza con `(.venv)`. Si no aparece, los comandos `vdc-navis-lab...` no funcionarán o usarán el Python general.

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

**Debes ver** `(.venv)` al inicio de la línea y, al final, `Successfully installed ... vdc-navis-lab-0.2.7`.

**Por qué siempre `.venv`:** sin él, pip mete las dependencias en el Python general y puede dañar otros programas. Pasó una vez: `mcp` trae versiones nuevas de `starlette` y `websockets`, y otros paquetes del equipo (por ejemplo `gradio` o `fastapi`) piden versiones más viejas. El aviso "dependency conflicts" dice exactamente eso. No afecta a vdc-navis-lab, solo a esas otras aplicaciones. Si alguna se rompió, abre una terminal **sin** entorno activo (sin `(.venv)`) y ejecuta:

```powershell
pip install "starlette<0.49" "websockets<12"
```

Con eso `fastapi` y `gradio` deberían volver a la normalidad (no se comprobó en tu equipo).

## 3. Actualizar a la última versión

### 3.1 Si vienes de la versión que se llamaba `navis-mcp` (una sola vez)

El producto ahora se llama `vdc-navis-lab`. Cambiaron los comandos: `navis-mcp` pasó a `vdc-navis-lab` y `navis-mcp-cli` a `vdc-navis-lab-cli`. Hazlo en este orden, en **una terminal preparada** (sección 0, con `(.venv)`):

1. Cierra Claude Desktop por completo (flecha `^` junto al reloj, clic derecho en el icono de Claude, Salir) y cierra la terminal donde tengas `simulate` con `Ctrl+C`.
2. Desinstala el paquete viejo:
   ```powershell
   pip uninstall -y navis-mcp
   ```
3. Trae el código nuevo:
   ```powershell
   git pull origin main
   ```
   Si dice que hay cambios locales o archivos sin seguimiento que se sobrescribirían, escribe `git fetch origin` y luego `git reset --hard origin/main`. Es seguro: tu copia no tiene ediciones propias y no toca tus archivos ignorados (`CLAUDE.md`, `contexto`, `historial.md`, `.venv`).
4. Instala con el nombre nuevo:
   ```powershell
   pip install -e ".[dev]"
   ```
   **Debes ver** `Successfully installed ... vdc-navis-lab-0.2.7`.
5. Reemplaza la entrada vieja de Claude Desktop por la nueva:
   ```powershell
   vdc-navis-lab-cli desktop-config --write
   ```
   **Debes ver** `removed the old 'navis-mcp' entry` y `vdc-navis-lab added to ...`.
6. Abre Claude Desktop. En la lista de conectores debe aparecer **vdc-navis-lab** (y ya no `navis-mcp`).
7. Prueba con `vdc-navis-lab-cli demo`.

### 3.2 Actualizaciones normales

Cuando se publique una mejora, en una terminal preparada (sección 0):

```powershell
git pull origin main
git log --oneline -1
```

La segunda línea muestra el commit en el que quedaste. No hace falta reinstalar: el entorno apunta directamente a la carpeta. Se escribe `git pull origin main` completo, porque `git pull` a secas no sabe de dónde bajar.

## 4. La prueba más fácil: el recorrido guiado

En una terminal preparada (sección 0):

```powershell
vdc-navis-lab-cli demo
```

En unos segundos recorre todo el flujo contra un Navisworks falso: estado, análisis, plan de cambios, ejecución y verificación. **Debes ver** cinco pasos numerados y al final "Listo.". No necesita nada más ni toca tus datos. En inglés: `vdc-navis-lab-cli demo --lang en`.

**Con esto ya comprobaste que todo funciona.** Conectar Claude Desktop (sección 5) es el paso siguiente y es opcional.

Otros comandos, en la misma terminal:

| Comando | Qué hace |
|---|---|
| `vdc-navis-lab-cli tools` | Lista las 14 herramientas |
| `vdc-navis-lab-cli call nw_status` | Llama una herramienta suelta |
| `vdc-navis-lab-cli sample examples\torre.json` | Crea un archivo de ejemplo (una torre de 5 niveles) |
| `vdc-navis-lab-cli analyze examples\torre.json --lang es` | Analiza un archivo y escribe el informe |

## 5. Conectar Claude Desktop, paso a paso

**Qué ejecutas tú y qué no.** Tú solo escribes `desktop-config` (una vez) y `simulate` (cada vez que quieras probar con el Navisworks falso). **Nunca escribas `vdc-navis-lab`** en una terminal: es el servidor y lo arranca Claude Desktop por su cuenta. Si lo escribes por error, muestra una nota y se cierra; no pasa nada.

### 5.1 Registrar vdc-navis-lab en Claude Desktop (una sola vez)

1. Abre una terminal preparada (sección 0).
2. Escribe:
   ```powershell
   vdc-navis-lab-cli desktop-config --write
   ```
   **Debes ver** `backup: ...` y `vdc-navis-lab added to ...claude_desktop_config.json`. El comando guarda una copia de respaldo del archivo y no toca tus otros servidores.
3. Si en cambio dice `is not valid JSON (line N ...)`, el archivo de configuración tiene un error previo y **no se escribió nada**. Corrígelo: cierra Claude Desktop, escribe `notepad "$env:APPDATA\Claude\claude_desktop_config.json"`, ve a la línea indicada con `Ctrl+G`, corrige o borra el texto sobrante, guarda y repite el paso 2.
4. Cierra Claude Desktop **por completo**: haz clic en la flecha `^` junto al reloj de Windows, clic derecho en el icono de Claude, Salir. Cerrar solo la ventana no basta.
5. Abre Claude Desktop de nuevo.

### 5.2 Usarlo con el Navisworks falso (cada vez)

1. Abre una terminal preparada (sección 0) y escribe:
   ```powershell
   vdc-navis-lab-cli simulate
   ```
   **Debes ver** `Navisworks simulator listening on tcp://127.0.0.1:...` y nada más. Es lo normal: el programa está esperando a que Claude le pregunte, no está colgado. **Deja esa terminal abierta**, sin escribir nada más en ella.
2. En Claude Desktop abre un chat nuevo. Pide: "Revisa el estado de Navisworks y analiza los problemas más graves".
3. La primera vez Claude pedirá permiso para usar la herramienta: acepta. **Debes ver** 35 problemas, uno crítico.
4. Al terminar, vuelve a la terminal del simulador y pulsa `Ctrl+C`.

### Registrar a mano (solo si no puedes usar el comando)

Abre `%APPDATA%\Claude\claude_desktop_config.json`. Si ya tiene `"mcpServers"`, **no pegues el bloque completo**: agrega solo la entrada `"vdc-navis-lab": {...}` dentro de ese objeto, con una coma después de la entrada anterior. Pegar un bloque nuevo después de la última llave `}` deja el archivo inválido y Claude Desktop no arranca ("Unexpected non-whitespace character after JSON"). El bloque completo, solo para un archivo vacío:

```json
{
  "mcpServers": {
    "vdc-navis-lab": {
      "command": "D:\\IA_WORK\\MCP_NAVIS\\.venv\\Scripts\\vdc-navis-lab.exe",
      "env": { "VDC_NAVIS_LAB_READ_ONLY": "1" }
    }
  }
}
```

### Claude Code

En una terminal preparada (sección 0):

```powershell
claude mcp add vdc-navis-lab -- D:\IA_WORK\MCP_NAVIS\.venv\Scripts\vdc-navis-lab.exe
```

## 6. Qué pedirle al asistente

- "Revisa el estado de Navisworks."
- "Analiza el archivo `D:\...\clash.xml` y dime los cinco problemas más graves."
- "¿Qué disciplinas no tienen resultados? ¿Qué pruebas nunca se ejecutaron?"
- "Dame el detalle del problema NW-9504F9."
- "Genera un informe en CSV y otro en BCF."
- "Agrupa los 20 problemas más graves." (primero muestra un plan; no cambia nada hasta que lo confirmes)

Para analizar tus propios clashes sin Navisworks conectado: en Navisworks, Clash Detective, pestaña Report, formato XML, y pásale la ruta del archivo al asistente. Los CSV y los JSON de vdc-navis-lab también sirven. Los exportes reales varían entre versiones; si uno falla, guárdalo y avisa, es información útil para mejorar el lector.

## 7. Seguridad: lo que conviene saber

- `VDC_NAVIS_LAB_READ_ONLY=1` bloquea toda escritura en Navisworks. `desktop-config` lo deja activado; si quieres permitir escrituras, vuelve a ejecutar el comando con `--allow-writes`.
- Los informes se guardan solo en `%USERPROFILE%\.vdc_navis_lab\exports`, salvo que definas `VDC_NAVIS_LAB_OUTPUT_ROOTS`.
- Cambiar algo en Navisworks siempre son dos pasos: un plan (que no modifica nada) y su ejecución por `plan_id`.

## 8. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `vdc-navis-lab-cli` no se reconoce como comando | La terminal no tiene el entorno: repite la sección 0 |
| `invalid choice: '...'` al escribir un comando del manual | Tu copia está desactualizada: sección 3 |
| `desktop-config` dice que el archivo no es JSON válido | Paso 3 de la sección 5.1 |
| Claude Desktop no muestra las herramientas | Ciérralo por completo (paso 4 de 5.1) y ábrelo otra vez |
| "no Navisworks instance" | Normal sin Navisworks: usa un archivo o deja `simulate` abierto en otra terminal |
| Un XML no se lee | Prueba con CSV o avisa del caso |
| Los resultados dicen "nunca ejecutada" | Esa prueba no se corrió en Navisworks: ausencia de clashes no significa que esté limpio |

## 9. Qué no hace todavía

Correr las pruebas de Clash Detective, un censo del modelo federado, crear viewpoints, colorear el modelo ni generar PDF. Ver [docs/ROADMAP.md](docs/ROADMAP.md).

## 10. Conectar con Navisworks Manage 2026 real

Se hace una sola vez por equipo y por versión de Navisworks. Requiere el SDK de .NET 8 (`dotnet --list-sdks` debe mostrar una versión 8) y el entorno de la sección 0.

**Paso 1. Copiar las DLL de Navisworks para compilar.** En PowerShell, desde cualquier carpeta (ajusta la ruta de la carpeta del proyecto si es distinta):

```powershell
$dst = "D:\IA_WORK\MCP_NAVIS\addin\refs\2026"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "C:\Program Files\Autodesk\Navisworks Manage 2026\Autodesk.Navisworks.*.dll" $dst
```

Debes ver, al listar esa carpeta, archivos `Autodesk.Navisworks.Api.dll` y `Autodesk.Navisworks.Clash.dll`. Esas DLL son de Autodesk: no se suben a GitHub (la carpeta está en `.gitignore`).

**Paso 2. Compilar, instalar y probar con un comando:**

```powershell
powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\todo.ps1
```

El script: espera a que cierres Navisworks, compila, instala el add-in en `%APPDATA%\Autodesk\Navisworks Manage 2026\Plugins\VdcNavisLab\`, te pide abrir Navisworks y un modelo, y corre las pruebas. Al final guarda en `insumos\` una muestra real de tus datos y el análisis.

**Qué debes ver:** `Compilación correcta`, `Pipe encontrado`, `Modelo abierto. Probando...`, el estado con tus pruebas de Clash Detective y un análisis con problemas ordenados.

**Si algo falla**, ejecuta con Navisworks abierto: `powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\check.ps1`. Muestra si Navisworks está corriendo, si el add-in está instalado, el log del add-in (`%LOCALAPPDATA%\vdc-navis-lab\addin.log`) y si existe el pipe.

Después de esto, el conector de Claude Desktop (sección 5) lee el Navisworks abierto sin que cambies nada más. Cada vez que actualices el proyecto (sección 3), vuelve a correr `todo.ps1` para reinstalar el add-in.
