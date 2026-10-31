---
name: agentes-personalizados
description: >-
  Guía y referencia completa para crear, configurar e invocar Agentes Personalizados
  (Custom Agents) en Google Antigravity (Antigravity 2.0 y Antigravity CLI). Úsala
  cuando el usuario pida crear un agente personalizado o subagente en formato Markdown
  (.md), configurar su frontmatter YAML (herramientas, skills, políticas de ejecución,
  permisos, simetría mainAgent/subagent), elegir dónde guardarlo (.agents/agents/ o
  global) o explicar cómo invocarlo.
---

# Agentes Personalizados (Custom Agents) en Antigravity

Los **Agentes Personalizados** (*Custom Agents*) son configuraciones basadas en archivos Markdown (`.md`) con encabezado YAML frontmatter que definen un rol especializado con sus propias instrucciones de sistema, herramientas (*tools*), habilidades (*skills*), modelo y restricciones de seguridad.

Resuelven dos limitaciones clave de los asistentes de propósito general:
1. **Falta de especialización**: Evitan tener que repetir las convenciones de pruebas, arquitectura o gestión de dependencias en cada conversación.
2. **Saturación de la ventana de contexto (*context window bloat*)**: A diferencia de cargar todas las reglas, habilidades y herramientas MCP en cada sesión, un agente personalizado filtra y vincula únicamente el subconjunto de *tools*, *skills* y servidores MCP relevantes para su dominio.

---

## 1. Dónde se guardan (Ubicación y Descubrimiento)

Antigravity descubre automáticamente los archivos de agentes personalizados según su alcance (*scope*):

| Alcance | Ruta del archivo | Propósito |
| :--- | :--- | :--- |
| **Proyecto / Workspace** *(Recomendado para equipos)* | `.agents/agents/<nombre>.md`<br>o `.agents/agents/<nombre>/agent.md` | Disponible automáticamente para cualquier miembro del equipo que clone el repositorio (control de versiones). |
| **Global del Usuario** | `~/.gemini/config/agents/<nombre>.md`<br>o `~/.gemini/config/agents/<nombre>/agent.md` | Disponible en todos los proyectos y espacios de trabajo de tu máquina local. |
| **Plugins** | `plugins/<nombre_plugin>/agents/<nombre>.md` | Empaquetado dentro de un plugin distribuible. |

> **Nota**: También se pueden definir subagentes efímeros (solo para la sesión activa) en tiempo de ejecución mediante la herramienta `define_subagent`.

---

## 2. Formato del Archivo de Agente

Un agente personalizado se compone de dos partes en un único archivo `.md`:
1. **Encabezado YAML Frontmatter** (entre delimitadores `---`): Define los metadatos, capacidades, permisos, modelo y políticas de ejecución del agente.
2. **Cuerpo Markdown**: Todo el contenido posterior al cierre `---` se compila directamente como el **System Prompt** (instrucciones de sistema) del agente. Se recomienda estructurarlo con encabezados Markdown (`# Core Instructions`, `# Review Guidelines`, etc.).

### Campos Soportados en el YAML Frontmatter

| Campo | Tipo | Valor por defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `name` | `string` | *(Obligatorio)* | Identificador único del agente (se recomienda formato `kebab-case`, ej. `dependency-modernizer`). |
| `description` | `string` | *(Obligatorio)* | Descripción clara del propósito del agente. El agente coordinador/planificador la usa para decidir cuándo delegarle tareas mediante descubrimiento progresivo. |
| `mainAgent` | `boolean` | `true` | Si es `true`, permite iniciar una sesión principal hablando directamente con este agente en la interfaz o CLI. |
| `subagent` | `boolean` | `true` | Si es `true`, permite que un agente coordinador lo invoque dinámicamente en segundo plano usando `invoke_subagent`. |
| `model` | `string` | `inherit` | Nivel de modelo a utilizar cuando se ejecuta (`inherit`, `flash`, `flash_lite` o `pro`). |
| `tools` | `string[]` | `[]` | Lista explícita de herramientas permitidas para el agente (ej. `view_file`, `replace_file_content`, `grep_search`, `manage_task`, `run_command`). |
| `skills` / `plugins` | `string[]` | `[]` | Rutas a las *skills* específicas o dependencias de plugins que el agente tendrá disponibles (ej. `skills/package-upgrade-rules`), evitando cargar todas las *skills* del workspace. |
| `permissionMode` | `string` | *(Heredado)* | Nivel general de permisos (ej. `acceptEdits`, `bypassPermissions`). |
| `commandExecutionPolicy` | `string` | `sandbox` | Política de auto-ejecución para comandos de terminal: `off`, `auto`, `eager` o `sandbox`. Con `auto`, el agente ejecuta pruebas y compilaciones estándar de forma autónoma mientras que los comandos de alto riesgo (como borrar archivos) siguen requiriendo aprobación manual. |
| `mcpServers` | `object[]` | `[]` | Servidores Model Context Protocol (MCP) configurados específicamente para este agente. |

> **Precaución sobre `tools`**: Especificar un nombre de herramienta inexistente o mal escrito en la lista `tools` puede hacer que el proceso del subagente se bloquee al iniciar. Verifica siempre que los nombres de las herramientas sean exactos.

---

## 3. Simetría de Ejecución y Cómo se Invocan

A diferencia de otras herramientas donde los agentes personalizados solo pueden actuar como subagentes secundarios, Antigravity ofrece **simetría de ejecución** (`mainAgent: true` y `subagent: true`):

### A. Como Agente Principal (`mainAgent: true`)
Interactúas directamente con el agente personalizado desde el inicio de la sesión; su cuerpo Markdown se convierte en el *system prompt* principal y la sesión adopta todos los parámetros de su frontmatter:
- **En Antigravity 2.0 (GUI)**: Selecciónalo directamente desde el menú desplegable (*dropdown*) de agentes al iniciar o cambiar la conversación.
- **En Antigravity CLI (`agy`)**:
  - Al lanzar desde la terminal:
    ```bash
    agy --agent <nombre-del-agente>
    # Ejemplo: agy --agent dependency-modernizer
    ```
  - Dentro de una sesión interactiva del CLI: ejecuta el comando `/agents` para abrir el panel **Agent Manager** y selecciona el agente personalizado como agente primario.

### B. Como Subagente Delegado (`subagent: true`)
Un agente principal o coordinador puede delegar tareas asíncronas en segundo plano al agente personalizado:
- **Invocación automática por el agente padre**: El agente principal llama a la herramienta `invoke_subagent` pasando `TypeName: "<nombre-del-agente>"`, un `Role` descriptivo, el `Prompt` con la tarea y el modo de `Workspace` (`inherit` para usar el mismo workspace, `branch` para un Git worktree aislado o `share` para compartir almacenamiento).
- **Aislamiento de contexto**: El subagente inicia con una ventana de contexto limpia (no hereda el historial de conversación del padre) y se ejecuta de forma asíncrona en paralelo.
- **Comunicación directa y monitoreo**:
  - **En la GUI (Antigravity 2.0)**: Abre el panel de subagentes para inspeccionar su progreso, detenerlo o escribirle directamente en su caja de mensajes.
  - **En el CLI (`agy`)**:
    - Usa `/agents` para ver el estado en vivo (`running`, `idle`, `killed`, `error`) y presiona `Enter` para abrir el *Subagent Detail View*.
    - Envía instrucciones directas desde el prompt principal con `@<nombre-subagente> <mensaje>`.
    - Usa `Alt+J` para saltar directamente al detalle de un subagente que espera aprobación de permisos, o `Ctrl+K` para aprobar rápidamente una acción pendiente (*fast-path*).

---

## 4. Plantillas y Ejemplos de Referencia

Puedes consultar o copiar las siguientes plantillas listas para usar incluidas en esta skill:
- [Ejemplo completo de modernizador de dependencias (`dependency-modernizer.md`)](./examples/dependency-modernizer.md)
- [Ejemplo de auditor de seguridad solo como subagente (`code-auditor.md`)](./examples/code-auditor.md)

### Plantilla Rápida (`.agents/agents/mi-agente.md`)

```markdown
---
name: dependency-modernizer
description: Helps upgrade local packages and verify that project tests pass.
model: flash
mainAgent: true
subagent: true
permissionMode: acceptEdits
commandExecutionPolicy: auto
tools:
  - view_file
  - replace_file_content
  - manage_task
  - run_command
skills:
  - skills/package-upgrade-rules
---

# Core Instructions

You are a dependency modernizer. Your job is to check configuration files,
update target dependencies, run test suites, and verify the build passes.
```

---

## 5. Flujo de Trabajo para Crear un Agente Personalizado

Cuando el usuario solicite crear un nuevo agente personalizado:
1. **Definir el alcance**: Si es para el proyecto actual, guárdalo en `.agents/agents/<nombre>.md`. Si pide explícitamente que sea global, usa `~/.gemini/config/agents/<nombre>.md`.
2. **Configurar el Frontmatter**:
   - Define `name` (en `kebab-case`) y un `description` claro y específico para el enrutador de subagentes.
   - Configura `mainAgent` y `subagent` según cómo quiera invocarlo el usuario (ambos `true` por defecto para máxima flexibilidad).
   - Selecciona el `model` adecuado (`flash` para tareas rápidas/iterativas, `pro` para auditorías o razonamiento complejo, `inherit` para heredar el modelo activo).
   - Restringe `tools` y `skills` únicamente a los necesarios para evitar contaminar la ventana de contexto.
   - Ajusta `permissionMode` y `commandExecutionPolicy` (ej. `auto` o `sandbox`) si el agente necesita ejecutar comandos de prueba o compilación sin interrumpir constantemente al usuario.
3. **Redactar el System Prompt**: Escribe en el cuerpo Markdown instrucciones concisas, reglas del dominio y pasos de verificación que el agente debe cumplir antes de dar por terminada su tarea.

