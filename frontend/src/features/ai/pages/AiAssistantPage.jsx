import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBranding } from '../../../hooks/useBranding'
import { AiAssistantWorkspace } from '../components/AiAssistantDrawer'

export default function AiAssistantPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { branding } = useBranding()
  const conversationId = searchParams.get('conversation')

  const handleActiveConversationChange = useCallback((activeConversationId) => {
    if (activeConversationId) {
      setSearchParams({ conversation: String(activeConversationId) }, { replace: true })
    } else {
      setSearchParams({}, { replace: true })
    }
  }, [setSearchParams])

  return (
    <div className="flex h-[calc(100dvh-9rem)] min-h-0 flex-col gap-4 overflow-hidden">
      <div className="shrink-0">
        <h1 className="page-title">{branding.assistant_name}</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Search prior conversations, continue project and requirement discussions, and review actions available to your account.
        </p>
      </div>

      <AiAssistantWorkspace
        mode="page"
        initialConversationId={conversationId}
        onActiveConversationChange={handleActiveConversationChange}
      />
    </div>
  )
}
