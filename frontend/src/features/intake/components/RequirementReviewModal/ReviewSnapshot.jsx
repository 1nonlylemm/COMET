import { DocumentEvidencePanel } from './DocumentEvidencePanel'

export { DocumentEvidencePanel }

/**
 * ReviewSnapshot — Requirement-Driven Documentary Evidence Header
 *
 * In Phase R6, this replaces the legacy score dial and compliance percentage
 * with the requirement-driven evidence verification panel.
 */
export function ReviewSnapshot(props) {
  return <DocumentEvidencePanel {...props} />
}

export default ReviewSnapshot

