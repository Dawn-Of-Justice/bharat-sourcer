import type { FabricationPlan, ReportLine } from './api'

// Made-to-order lines: ordered from a fabrication service, never from a seller (see MadeToOrder.tsx).
export const madeToOrder = (line?: ReportLine | null): line is ReportLine & { fabrication: FabricationPlan } =>
  !!line && !line.item.user_has_it && line.sourcing_status === 'fabrication_service' && !!line.fabrication

export const kindLabel = (plan: FabricationPlan) => (plan.kind === 'pcb' ? 'PCB fab service' : '3D printing service')
