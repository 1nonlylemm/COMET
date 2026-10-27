import { Modal } from './Modal'
import { Button } from './Button'
import { AlertTriangle } from 'lucide-react'

export function ConfirmationModal({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onClose,
  loading = false,
  isDestructive = false,
}) {
  const footer = (
    <div className="flex justify-end gap-3">
      <Button variant="outline" onClick={onClose} disabled={loading}>
        {cancelLabel}
      </Button>
      <Button variant={isDestructive ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
        {confirmLabel}
      </Button>
    </div>
  )

  return (
    <Modal
      open={open}
      title={title}
      description={description}
      size="sm"
      onClose={onClose}
      footer={footer}
    >
      {isDestructive && (
        <div className="flex items-start gap-3 rounded-md bg-red-50 p-3 text-red-700 dark:bg-red-500/10 dark:text-red-400">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <p className="text-sm">This action is destructive and cannot be undone.</p>
        </div>
      )}
    </Modal>
  )
}
