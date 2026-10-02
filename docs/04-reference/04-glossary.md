# Glossary

| Term | Meaning |
|---|---|
| **A2A** | Agent2Agent protocol (v1.0, Linux Foundation). Lets agents from different systems talk to each other |
| **A2UI** | Google's open spec for agent-generated UI (v0.9). The agent sends declarative component JSON and the client renders it |
| **ADK** | Agent Development Kit, Google's open-source agent framework. 2.x adds graph `Workflow`s |
| **AG-UI** | Agent–User Interaction protocol for streaming agent events and state to a frontend (used with CopilotKit) |
| **Agent Platform** | "Gemini Enterprise Agent Platform", the 2026 name for Vertex AI. Agent Engine became *Agent Runtime* |
| **Agentic video understanding** | Gemini mode (`processing: "agentic"`, 1 Sep 2026) in which the model navigates the video timeline and loads only what it needs |
| **AP2** | Agent Payments Protocol: verifiable mandates for agent-initiated payments |
| **ATL** | Atal Tinkering Lab, a government-funded maker lab in Indian schools |
| **BCD / SWS / IGST** | Basic Customs Duty / Social Welfare Surcharge / Integrated GST, the components of Indian import tax |
| **BIS** | Bureau of Indian Standards. Mandatory registration covers many electronics categories |
| **BOM** | Bill of Materials: the parts list with quantities |
| **CHIMS** | Chip Imports Monitoring System, an Indian registration for importing chips |
| **Desi BOM** | Our name for the output: an India-sourced, costed, compatibility-checked BOM |
| **DPDP Act** | India's Digital Personal Data Protection Act, 2023 |
| **Drop-in** | Replacement needing no wiring or code change (grade A) |
| **Ecosystem** | A connector/form-factor family, e.g. STEMMA QT, Qwiic, Grove, Feather, Pololu stepper footprint |
| **FQBN** | Fully Qualified Board Name in arduino-cli, e.g. `esp32:esp32:esp32` |
| **File Search** | Gemini API managed RAG over uploaded files, with page-level citations |
| **Grounding (Search / Maps)** | A Gemini tool that runs Google Search or Maps queries and returns cited results |
| **Human-in-the-loop (HITL)** | The confirm-parts step where the user edits the extracted BOM |
| **I2C address** | 7-bit bus address (e.g. 0x76 / 0x77 for BME280). Clashes and defaults matter |
| **Interactions API** | Gemini's recommended API (`client.interactions.create`) for models and agents |
| **KG** | Our curated knowledge graph of chips, modules, libraries, boards and ecosystems |
| **Landed cost** | Item + international shipping + duties/taxes, i.e. the true import cost |
| **Level shifter** | Circuit that converts 5 V ↔ 3.3 V logic signals (e.g. 74AHCT125, BSS138) |
| **Listing** | A verified seller product page with price, stock and fetch time. Only listings are shown to users |
| **Look-alike** | Parts that look identical but differ (BME280 vs BMP280, SSD1306 vs SH1106) |
| **Mains** | AC line power: 230 V / 50 Hz in India, 120 V / 60 Hz in the US |
| **MCP** | Model Context Protocol, a standard for exposing tools to AI agents |
| **Module** | A breakout board carrying a chip (e.g. GY-BME280), as opposed to the chip itself |
| **MPN** | Manufacturer Part Number |
| **NPCI UAP** | National Payments Corporation of India's Unified Agent Protocol for agentic UPI payments |
| **ONDC / Beckn** | India's Open Network for Digital Commerce and its underlying open protocol |
| **Qwiic / STEMMA QT** | SparkFun and Adafruit I2C ecosystems. Both use JST-SH 1 mm 4-pin connectors with the same pin order, so they're interchangeable |
| **Silkscreen** | Printed text on a PCB, which we read verbatim from video frames |
| **SMPS** | Switched-mode power supply |
| **SSR** | Solid-state relay |
| **Open discovery** | Our sourcing principle: no fixed seller list. Any Indian seller found by web search, the Shopify Global Catalog or protocol probes can appear, with a trust label |
| **Seed sellers** | ~25 hand-checked stores that form the registry's starting point: a fast path, not a limit |
| **Trust label** | Established / Verified basics / Unverified / Blocked, computed from Web Risk, domain age, HTTPS, GSTIN, policies, price anomaly and votes |
| **RDAP** | Registration Data Access Protocol, the structured successor to WHOIS. Gives domain creation dates |
| **Web Risk API** | Google Cloud API that checks URLs against malware and social-engineering lists |
| **UCP** | Universal Commerce Protocol (Google + Shopify, Jan 2026). Merchants publish `/.well-known/ucp`, and Shopify stores expose MCP catalog tools |
| **URL context** | A Gemini tool that fetches and reads up to 20 URLs per request |
| **Vref** | Reference voltage that sets a stepper driver's current limit. The formula differs by driver |
