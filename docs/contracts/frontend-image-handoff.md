# Product images and concurrent progress

The frontend accepts optional nullable report.lines[].offers[].image_url (HTTP/HTTPS). This is a proposed backend field, not part of the current published API schema. No backend routes or schemas changed.

Completed parts display the first available offer image in a square beside their details. Missing or failed images show Image unavailable. The backend should provide the corresponding seller product image URL. Update the schema and regenerate OpenAPI when implementing it.

Progress matches report lines by line_id, so results can arrive in any order. Owned parts and terminal outcomes count as completed. Absent lines and not_run remain pending. The contract has no per-part running state; the UI does not invent one. Concurrent scheduling remains backend work.
