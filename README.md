# Meeting Closure Assistant

**[Live Demo — Try Meeting Closure Assistant](https://meeting-closure-assistant-dcghnju4mfmjxr79wbf4tp.streamlit.app/)**

An agenda-aware AI meeting assistant that helps teams check whether important meeting outcomes are sufficiently closed or appropriately handed off before a meeting ends. It evaluates progress against the meeting’s purpose, alongside a structured summary of what was discussed.

## Problem

Meeting tools often focus on post-meeting summaries. This project focuses on an earlier question:

> Before we end this meeting, have we actually accomplished what we came here to do?

Common gaps include agenda items discussed but not completed, unresolved decisions, responsibilities without clear ownership, and important topics not meaningfully addressed. Which gaps matter depends on the meeting: not every meeting requires decisions, owners, or deadlines.

## Product Approach

```text
Meeting Type + Meeting Goal + Agenda + Transcript
                        ↓
                   AI analysis
                        ↓
             Overall Meeting Progress
                        ↓
             Before Ending This Meeting
                        ↓
                  Agenda Review
                        ↓
                 Meeting Summary
```

Meeting Type, Goal, and Agenda provide context for interpreting what “complete” means. The specific goal and agenda take precedence over assumptions about the meeting type.

Two principles guide the analysis:

1. **Agenda completion is not the same as underlying work completion.**  
   “Review marketing readiness” can be completed when the current status is sufficiently reviewed, even if final image approval remains pending.

2. **Unresolved does not automatically mean it must be solved before the meeting ends.**  
   An external dependency may remain open when ownership, follow-up, and next steps are sufficiently clear for this meeting’s purpose.

Decisions, action items, owners, deadlines, blockers, and risks are contextual closure signals—not universal requirements. The **Before Ending This Meeting** section highlights outstanding items that genuinely need attention before the current meeting ends.

## Features

- Meeting Type, Goal, Agenda, and Transcript inputs, including a custom meeting type.
- Agenda-aware classification with supporting reasons:
  - **Completed:** the intended outcome was achieved.
  - **Unresolved:** meaningfully discussed, but the intended outcome remains unmet.
  - **Missing:** not meaningfully addressed.
- Overall progress toward the meeting’s intended outcomes.
- Prioritized visibility for **Before Ending This Meeting** recommendations.
- Structured summary containing:
  - Key decisions.
  - Action items with owners and deadlines when available.
  - Risks and unresolved issues.
- Editable inputs after analysis, with an outdated-results notice when inputs change.
- Manual re-analysis through **Prepare to End Meeting**.

## Architecture

```text
Streamlit UI
    → Python application
    → One DeepSeek API call per analysis
    → Structured JSON response
    → Python parsing
    → Streamlit result rendering
```

Analysis and summary are requested together. This single-call design keeps the MVP simple and avoids separate summarization requests, reducing API overhead, latency, and cost.

The application checks for empty, truncated, or invalid JSON responses and displays a concise error message when analysis cannot be completed.

## Tech Stack

- Python — tested with Python 3.12.
- Streamlit — user interface and session state.
- DeepSeek API — `deepseek-flash`, accessed through the OpenAI-compatible Python SDK.
- python-dotenv — local environment-variable loading.

Dependency versions are pinned in `requirements.txt`.

## Running Locally

1. Clone this repository and open its directory:

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Install dependencies, preferably in a virtual environment:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to a new file named `.env`.

4. Set your DeepSeek API key in `.env`:

   ```dotenv
   DEEPSEEK_API_KEY=your_key_here
   ```

   Replace the placeholder with your own key. `.env` is excluded from Git.

5. Start the application:

   ```bash
   streamlit run app.py
   ```

6. Open the local URL shown in the terminal. Enter the meeting context and transcript, then click **Prepare to End Meeting**.

Meeting Goal, Agenda, and Transcript are required. Analysis sends the supplied meeting inputs to DeepSeek.

## State and Re-analysis

The last successful result and its input snapshot are stored in Streamlit session state.

- Inputs remain editable after analysis.
- Editing an input does not trigger an API call.
- When inputs differ from the analyzed snapshot, the previous result remains visible with an outdated-results notice.
- Clicking **Prepare to End Meeting** requests a new analysis.
- A successful analysis replaces the previous result and snapshot; a failed request preserves the last successful result.
- The custom “Other” meeting type description is retained when switching types.

State is session-only and does not persist across a new browser or app session.

## Deployment

To deploy on Streamlit Community Cloud:

1. Push the project to GitHub, including `app.py` and `requirements.txt`.
2. Select the repository and `app.py` as the entry point.
3. Choose Python 3.12. Community Cloud installs dependencies from `requirements.txt`.
4. Configure `DEEPSEEK_API_KEY` as a root-level secret in the Cloud app settings; it is made available as an environment variable.

Never upload `.env` or commit credentials to the repository.

## Limitations

- Transcripts must currently be pasted manually; there is no real-time transcript ingestion.
- There is no persistent meeting history or database.
- Output quality depends on transcript quality and the model’s interpretation.
- Agenda classification is semantic rather than deterministic.
- Progress is a model-generated assessment, not an objective measurement.
- Recommendations support human judgment and do not guarantee meeting effectiveness.

## Future Improvements

- Real-time transcript ingestion.
- Pre-meeting agenda integration.
- Meeting history and follow-up tracking.
- Configurable closure criteria for teams.
- Integrations with collaboration tools.
