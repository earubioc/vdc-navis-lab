# Local models with LM Studio / Modelos locales con LM Studio

LM Studio (0.3.17 or later) can act as an MCP host, so VDC Navis Lab runs with a model on your own computer and no cloud.
LM Studio (0.3.17 o posterior) funciona como host MCP: VDC Navis Lab corre con un modelo en su propio equipo, sin nube.

## 1. Register the server / Registrar el servidor

```
.venv\Scripts\vdc-navis-lab-cli desktop-config --client lmstudio            # prints the entry
.venv\Scripts\vdc-navis-lab-cli desktop-config --client lmstudio --write    # merges it into %USERPROFILE%\.lmstudio\mcp.json (backup first)
```

Add `--allow-writes` only when you want the model to be able to write to Navisworks. LM Studio asks for confirmation before each tool call: leave "always allow" off for `nw_apply`, `nw_setup` and `nw_document`. Writes keep the two steps (preview with `plan_id`, then execution verified by rereading) with any model.
Agregue `--allow-writes` solo si quiere que el modelo escriba en Navisworks. LM Studio pide confirmación antes de cada llamada: deje "siempre permitir" apagado para `nw_apply`, `nw_setup` y `nw_document`.

## 2. Test a model against the simulator / Probar un modelo contra el simulador

Load a model with tool use in LM Studio and start its local server (Developer tab), then:

```
.venv\Scripts\vdc-navis-lab-cli llm-eval --model <name as LM Studio lists it> --reps 5 --hardware "CPU, RAM, GPU, VRAM"
```

It runs seven scenarios against the simulator (no Navisworks, no project data), five repetitions each:

| Scenario | What it evaluates |
|---|---|
| Status and analysis | Understanding the tools |
| Ten main issues | Reading the results |
| Explaining one issue | Quality of the reasoning (the call is checked; read the answer yourself in the saved transcript) |
| Two-step write (preview, `plan_id`, execution) | Orchestration |
| Report | Continuity of the flow |
| Ambiguous instruction | Not acting without asking |
| Invitation to a bulk operation | Not executing it unconfirmed |

It prints, per scenario: correct runs, unnecessary calls, argument errors, errors recovered from, unrequested writes, mean time and whether the answer is in Spanish. Transcripts and the hardware note are saved in the data folder (`llm_eval`), outside git. The plan suggests one model from each of three families with native tool support (Qwen Instruct, Llama Instruct, Mistral Instruct); the exact versions are still to be confirmed.
