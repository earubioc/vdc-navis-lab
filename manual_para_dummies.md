# VDC Navis Lab: manual para dummies

Guía para instalar y probar **VDC Navis Lab 1.0** desde cero en un computador Windows, sin saber programar. Cada paso dice **dónde** se escribe y **qué debes ver**. Si algo no coincide con lo que dice el manual, ve a la sección 10 y a la 11 (cómo avisar del problema, que es información útil para mejorar el programa).

English version: [manual_for_dummies.md](manual_for_dummies.md).

## 0. Antes de empezar

- **Tiempo:** unos 20 minutos si todo sale bien. La mayor parte es esperar descargas.
- **Hace falta internet** durante la instalación.
- **No hacen falta permisos de administrador** para instalar este programa. Sí pueden hacer falta para instalar Python, .NET y Claude Desktop, si no están.
- **Una advertencia honesta sobre la versión de Navisworks.** El add-in (la pieza que habla con Navisworks) está **verificado solo en Navisworks Manage 2026**. Para 2023, 2024 y 2025 el instalador intenta compilarlo contra tu Navisworks, pero eso **no se ha probado**: puede funcionar o puede dar errores. La sección 3 explica cómo saber qué versión tienes y qué esperar. Todo lo que no depende del add-in (la demo, analizar archivos exportados, los informes) funciona igual en cualquier versión.

## 1. Qué es, en una frase

Un puente entre un asistente de IA (Claude) y Navisworks Manage. La IA no recibe miles de filas crudas de clashes: recibe una lista de problemas ordenada por prioridad, con la razón de cada uno, quién debe moverse y qué falta por revisar. Además puede preparar el proyecto (conjuntos de búsqueda por disciplina y pruebas de Clash Detective), agrupar, colorear y generar informes. Todo lo que cambia el modelo se hace en dos pasos: primero un plan que no toca nada, luego la ejecución, que se verifica releyendo el documento.

## 2. Qué debes tener instalado

| Programa | Para qué | Cómo comprobar | Cómo instalar |
|---|---|---|---|
| **Python 3.11 o superior** | Corre el programa | PowerShell: `python --version` (debe decir 3.11 o más) | https://www.python.org/downloads/ . **Marca la casilla "Add python.exe to PATH"** en la primera pantalla del instalador |
| **SDK de .NET 8** | Compila el add-in de Navisworks | PowerShell: `dotnet --list-sdks` (debe haber una línea que empiece por `8.`) | `winget install Microsoft.DotNet.SDK.8` o https://dotnet.microsoft.com/download |
| **Claude Desktop** | El asistente que usa el programa | Está en el menú Inicio | https://claude.ai/download |
| **Navisworks Manage** | El programa de BIM | Menú Inicio | (el que ya tienes) |

Para abrir PowerShell: menú Inicio, escribe `PowerShell`, Enter. **Después de instalar Python o .NET, cierra esa ventana y abre otra**; si no, no reconocerá los programas nuevos.

Si `python --version` abre la tienda de Microsoft o no dice nada, Python no está instalado como se necesita: instálalo desde python.org con la casilla marcada.

## 3. Qué versión de Navisworks tengo y qué esperar

Cómo saberlo, cualquiera de las dos:

- Mira las carpetas de `C:\Program Files\Autodesk`: se llaman `Navisworks Manage 2025`, `Navisworks Manage 2023`, etc.
- En Navisworks: pestaña Archivo, Ayuda, Acerca de.

| Versión | Estado | Qué hacer |
|---|---|---|
| **Manage 2026** | Verificado en un modelo real | Instalación normal |
| **Manage 2025** o **2024** | Sin probar. El instalador compila contra las DLL de tu versión; si Autodesk cambió alguna función que usa el add-in, la compilación **dará errores** | Instala igual (sección 5). Si compila y carga, prueba la sección 7 y cuenta qué funcionó. Si da errores, guarda `instalacion.log` (sección 11): sirve para corregirlo |
| **Manage 2023** o anterior | Sin probar y menos probable que funcione | Igual que arriba. Si falla, no es un error tuyo |
| **Simulate** o **Freedom** | No sirven: no tienen Clash Detective con API | Hace falta Manage |

**Si el computador tiene dos versiones** (por ejemplo 2023 y 2025), el instalador intenta ambas y dice cuáles quedaron instaladas. Eso es normal y no estorba: cada versión usa su propia carpeta.

**Cuál abrir para probar:** la más nueva de las que quedaron instaladas. Si una compiló y la otra no, abre la que compiló.

**Qué pasa si el add-in no funciona en tu versión:** el resto sigue sirviendo. Puedes analizar los clashes exportando el reporte desde Clash Detective (pestaña Reporte, formato XML) y pasándole la ruta del archivo al asistente. No tiene la escritura en el modelo, pero sí el análisis, el orden de prioridad y los informes.

## 4. Descargar el programa

1. Abre https://github.com/earubioc/vdc-navis-lab/releases/latest en el navegador. Es la última versión publicada.
2. Al final de la página, en "Assets", haz clic en **Source code (zip)**.
3. Abre el ZIP descargado y copia la carpeta de adentro a `C:\VDC`. Si `C:\VDC` no existe, créala. **Cambia el nombre de la carpeta a `vdc-navis-lab`** (el ZIP la trae con el nombre y la versión, por ejemplo `vdc-navis-lab-1.0.1`). Queda `C:\VDC\vdc-navis-lab`.

**Por qué ahí:** una ruta corta, sin espacios ni tildes ni carpetas sincronizadas (OneDrive, Escritorio) evita problemas. Puedes usar otra ruta que cumpla eso; en el manual se llama "la carpeta del programa".

(Si ya usas git: `git clone https://github.com/earubioc/vdc-navis-lab.git`.)

## 5. Instalar, con un solo comando

1. Abre la carpeta del programa en el Explorador de archivos.
2. Haz clic en la barra de direcciones (donde dice la ruta), borra lo que hay, escribe `powershell` y pulsa Enter. Se abre una ventana azul de PowerShell **ya ubicada en esa carpeta**. (Alternativa: abre PowerShell y escribe `cd C:\VDC\vdc-navis-lab`.)
3. **Cierra Navisworks** si lo tienes abierto.
4. Pega y pulsa Enter:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
   ```
5. Espera. Verás cuatro bloques:

| Bloque | Qué debes ver |
|---|---|
| `=== 1. Python y paquete` | `Python 3.12 (py)` (o tu versión) y, tras un rato de descargas, `Successfully installed ... vdc-navis-lab-1.0.0` |
| `=== 2. Prueba sin Navisworks (demo)` | Cinco pasos numerados y al final `Listo.` |
| `=== 3. Registrar en Claude Desktop` | `backup: ...` y `vdc-navis-lab added to ...claude_desktop_config.json` |
| `=== 4. Add-in de Navisworks` | `Versiones de Navisworks Manage: 2025` (las que haya), la compilación, y `3/3 Done. Installed in: ...\Plugins\VdcNavisLab` |

6. Al final aparece un cuadro verde con `LISTO. Siguiente:`. Eso es éxito.

El script deja un registro de todo en `instalacion.log`, dentro de la carpeta del programa.

**Si algo sale en rojo**, no repitas a ciegas: lee el mensaje (casi siempre dice qué falta, por ejemplo Python o .NET) y mira la tabla de la sección 10.

### Después de instalar

1. **Cierra Claude Desktop por completo.** Cerrar la ventana no basta: haz clic en la flecha `^` junto al reloj de Windows, clic derecho en el icono de Claude, **Salir**. Luego ábrelo de nuevo.
2. **Abre Navisworks Manage** y un modelo con pruebas de Clash Detective (o sin ellas; el programa también puede crearlas).
3. Pasa a la sección 7.

## 6. Si prefieres hacerlo a mano (o el script falló en un punto)

Cada línea se escribe en PowerShell, en la carpeta del programa.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
vdc-navis-lab-cli demo
vdc-navis-lab-cli desktop-config --write
```

- La segunda línea debe dejar `(.venv)` al inicio de la línea. Si dice que la ejecución de scripts está deshabilitada, escribe una sola vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, responde `S` y repite.
- **Por qué `.venv`:** instala el programa en una carpeta propia y no mezcla paquetes con el Python general (otros programas, como `gradio` o `fastapi`, piden versiones distintas de algunas librerías).

El add-in (con Navisworks cerrado), cambiando `2025` por tu versión:

```powershell
powershell -ExecutionPolicy Bypass -File .\addin\build-and-install.ps1 -Version 2025
```

Copia solo las cuatro DLL de Navisworks que necesita desde `C:\Program Files\Autodesk\Navisworks Manage 2025`, compila e instala en `%APPDATA%\Autodesk\Navisworks Manage 2025\Plugins\VdcNavisLab\`. Esas DLL son de Autodesk: no se suben a GitHub ni se comparten.

## 7. La primera prueba

### 7.1 Sin Navisworks: la demo

```powershell
.\.venv\Scripts\Activate.ps1
vdc-navis-lab-cli demo
```

**Debes ver** cinco pasos numerados y `Listo.`. No toca tus datos. Con esto ya está comprobado que el programa funciona. En inglés: `vdc-navis-lab-cli demo --lang en`.

### 7.2 Con Navisworks real

Con Navisworks abierto y un modelo cargado, en PowerShell, en la carpeta del programa:

```powershell
powershell -ExecutionPolicy Bypass -File .\addin\check.ps1
```

**Debes ver** cuatro bloques: Navisworks corriendo (`Roamer`), el plugin instalado (`VdcNavisLab.dll`), el registro del add-in (`addin.log`) con líneas recientes, y un pipe llamado `vdc-navis-lab.<número>`. Si los cuatro están, el add-in cargó.

Después, en Claude Desktop, abre un chat nuevo y escribe:

> Revisa el estado de Navisworks.

La primera vez Claude pide permiso para usar la herramienta: acepta. **Debes ver** el nombre del documento abierto, cuántas pruebas de Clash Detective tiene y si el programa está en modo solo lectura.

Y para la prueba grande:

> Analiza los problemas más graves y dime los cinco primeros con su razón.

(En un modelo grande tarda: lee los clashes de Clash Detective.)

## 8. Qué pedirle al asistente

| Quieres | Escribe |
|---|---|
| Saber si está conectado | "Revisa el estado de Navisworks." |
| Ver lo importante | "Analiza los clashes y dame los cinco problemas más graves." |
| Entender un problema | "Dame el detalle del problema NW-9504F9." |
| Revisar el modelo | "Haz una auditoría del modelo: ¿hay modelos vacíos, duplicados, lejos del resto o disciplinas que faltan?" |
| Preparar el proyecto | "Prepara los conjuntos de búsqueda por disciplina y las pruebas de clash entre ellas." (primero muestra un plan; nada cambia hasta que confirmes) |
| Correr las pruebas | "Corre las pruebas de clash." |
| Organizar | "Agrupa los problemas por nivel." / "Agrupa por par de disciplinas y nivel." |
| Ver en el modelo | "Selecciona en Navisworks los elementos del problema NW-9504F9 y coloréalos." (es temporal; no cambia el archivo) |
| Informes | "Genera el informe en PDF y el de entrega a coordinación." / "Genera CSV y BCF." |
| Sin Navisworks | "Analiza el archivo `C:\...\clash.xml`." |

Las 16 herramientas internas (`nw_status`, `nw_connect`, `nw_document`, `nw_profile`, `nw_snapshot`, `nw_analyze`, `nw_issues`, `nw_issue`, `nw_query`, `nw_model`, `nw_report`, `nw_run`, `nw_apply`, `nw_setup`, `nw_view`, `nw_job`) las elige el asistente solo; no tienes que escribir sus nombres. La lista detallada está en [docs/TOOLS.md](docs/TOOLS.md).

## 9. Seguridad: lo que conviene saber

- El instalador deja el programa en **solo lectura** (`VDC_NAVIS_LAB_READ_ONLY=1`): puede leer, analizar y colorear temporalmente, pero **no crea ni modifica nada en el documento**. Para permitir cambios (crear conjuntos y pruebas, agrupar, guardar): `.\instalar.ps1 -AllowWrites`, o `vdc-navis-lab-cli desktop-config --write --allow-writes`, y reinicia Claude Desktop.
- Aun con escritura permitida, todo cambio es en dos pasos: un plan (que no toca nada) y su ejecución por `plan_id`, que revisa de nuevo el documento antes de hacer algo y verifica el resultado al terminar.
- **Haz una copia del .nwd/.nwf antes de la primera prueba con escritura.** Por prudencia, no porque se haya visto un daño.
- Los informes se guardan solo en `%USERPROFILE%\.vdc_navis_lab\exports`.
- El programa no envía tus modelos a ningún servidor propio. Lo que Claude lee de Navisworks va a la conversación con Claude, como cualquier otro dato que le des.

## 10. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `python` no se reconoce, o abre la tienda de Microsoft | Instala Python desde python.org con "Add python.exe to PATH". Cierra PowerShell y abre otra |
| `No se encontro Python 3.11 o superior` | Igual: puede que tengas una versión vieja (3.9, 3.10) |
| `dotnet` no se reconoce | `winget install Microsoft.DotNet.SDK.8`, cierra PowerShell y abre otra |
| `No se encontro Navisworks Manage ...` | Instalaste una versión que no es Manage, o está en otra ruta. La parte de Python quedó instalada. Escribe `.\instalar.ps1 -Navisworks 2025` para forzar la versión |
| `Missing in ...refs\2025: Autodesk.Navisworks...` | No están las DLL de Autodesk donde se esperaba. Mira `C:\Program Files\Autodesk\Navisworks Manage 2025` y avisa qué archivos `Autodesk.Navisworks.*.dll` hay |
| Errores de compilación (`error CS...`) | El add-in usa una función que tu versión de Navisworks no tiene. Es el caso previsto para 2023/2024/2025: **guarda `instalacion.log` y avisa** (sección 11) |
| `Build failed` por no poder descargar paquetes | Falta internet o un proxy bloquea NuGet |
| `Navisworks is running` | Ciérralo (el script espera). Mira también el Administrador de tareas: debe desaparecer `Roamer.exe` |
| `check.ps1` dice `NO pipe` | Navisworks no cargó el add-in. Mira el bloque 3 (`addin.log`) y el 2 (¿está el `.dll`?). Si el plugin está pero no carga, puede ser la versión: sección 11 |
| Navisworks pregunta si confías en el plugin al abrir | Elige cargarlo. Es el add-in que acabas de instalar |
| Claude Desktop no muestra la herramienta `vdc-navis-lab` | Ciérralo **por completo** (flecha `^`, clic derecho, Salir) y ábrelo otra vez. Revisa Configuración, Desarrollador |
| `desktop-config` dice que el archivo no es JSON válido | El archivo `%APPDATA%\Claude\claude_desktop_config.json` tiene un error previo y no se escribió nada. Cierra Claude Desktop, ábrelo con el Bloc de notas, corrige la línea que indica y repite |
| "no Navisworks instance" | Navisworks está cerrado, sin modelo, o el add-in no cargó |
| Los resultados dicen "nunca ejecutada" | Esa prueba no se corrió en Navisworks: que no haya clashes no significa que esté limpio |
| El análisis se ve raro en un modelo propio | Los pesos de prioridad están calibrados con un solo modelo. Avisa con un ejemplo concreto |

## 11. Cómo avisar de un problema (esto es lo que más ayuda)

Envía estos tres datos a quien te dio el programa:

1. **`instalacion.log`**, que está en la carpeta del programa. Tiene todo lo que el instalador mostró, incluidos los errores.
2. **Tu versión de Navisworks** (sección 3) y si el computador tiene más de una.
3. Si ya está instalado y no responde, el resultado de `.\addin\check.ps1` con Navisworks abierto: selecciona el texto con el ratón, pulsa Enter para copiarlo y pégalo en un mensaje. También sirve una foto de la pantalla.

No hace falta entender el error. "Dio error en el paso 4 con Navisworks 2025" más el `instalacion.log` es suficiente.

## 12. Actualizar

Si bajaste el ZIP: descarga el ZIP nuevo y repite la sección 4 y la 5 en otra carpeta o sobre la misma (con Navisworks cerrado). Si usas git: `git pull origin main` en la carpeta del programa y luego `.\instalar.ps1`.

## 13. Desinstalar

1. Cierra Navisworks y Claude Desktop.
2. Borra la carpeta `%APPDATA%\Autodesk\Navisworks Manage <versión>\Plugins\VdcNavisLab`.
3. En `%APPDATA%\Claude\claude_desktop_config.json` borra la entrada `"vdc-navis-lab"` (hay copias de respaldo `.bak` al lado).
4. Borra la carpeta del programa.

## Apéndice: cómo está organizado

- `instalar.ps1`: instala todo.
- `addin\`: el add-in de Navisworks (`build-and-install.ps1`, `check.ps1`, `probar.ps1`, `todo.ps1`). Ver [addin/README.md](addin/README.md).
- `src\`: el programa en Python. `docs\`: documentación técnica. `examples\`: archivos de ejemplo.
- Licencia Apache 2.0. Proyecto independiente de VDC Process Lab, sin relación con Autodesk.
