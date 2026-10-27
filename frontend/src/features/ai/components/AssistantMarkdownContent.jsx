import React, { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SAFE_PROTOCOL_REGEX = /^(https?:\/\/|\/|#|mailto:)/i

function SafeLink({ href, children, ...props }) {
  const trimmed = typeof href === 'string' ? href.trim() : ''
  if (!trimmed || trimmed.startsWith('//') || !SAFE_PROTOCOL_REGEX.test(trimmed)) {
    return <span>{children}</span>
  }
  const isExternal = /^https?:\/\//i.test(trimmed)
  return (
    <a
      href={trimmed}
      target={isExternal ? '_blank' : undefined}
      rel={isExternal ? 'noreferrer noopener' : undefined}
      className="font-medium text-brand-primary underline hover:text-brand-primary/80 dark:text-blue-400 break-all"
      {...props}
    >
      {children}
    </a>
  )
}

const MarkdownComponents = {
  h1: ({ children, ...props }) => (
    <h1 className="mt-3 mb-1.5 text-base font-bold text-brand-text dark:text-slate-100" {...props}>
      {children}
    </h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 className="mt-2.5 mb-1 text-sm font-bold text-brand-text dark:text-slate-100" {...props}>
      {children}
    </h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="mt-2 mb-0.5 text-xs font-bold uppercase tracking-wider text-brand-text dark:text-slate-200" {...props}>
      {children}
    </h3>
  ),
  p: ({ children, ...props }) => (
    <p className="my-1.5 leading-relaxed first:mt-0 last:mb-0" {...props}>
      {children}
    </p>
  ),
  ul: ({ children, ...props }) => (
    <ul className="my-1.5 list-disc pl-5 space-y-0.5 leading-relaxed" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="my-1.5 list-decimal pl-5 space-y-0.5 leading-relaxed" {...props}>
      {children}
    </ol>
  ),
  li: ({ children, ...props }) => (
    <li className="leading-relaxed" {...props}>
      {children}
    </li>
  ),
  strong: ({ children, ...props }) => (
    <strong className="font-semibold text-brand-text dark:text-slate-100" {...props}>
      {children}
    </strong>
  ),
  em: ({ children, ...props }) => (
    <em className="italic" {...props}>
      {children}
    </em>
  ),
  code: ({ inline, className, children, ...props }) => {
    if (inline) {
      return (
        <code
          className={`rounded bg-slate-100 px-1 py-0.5 font-mono text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-200 ${className || ''}`.trim()}
          {...props}
        >
          {children}
        </code>
      )
    }
    return (
      <code className={`font-mono text-xs text-slate-100 ${className || ''}`.trim()} {...props}>
        {children}
      </code>
    )
  },
  pre: ({ children, ...props }) => (
    <pre
      className="my-2 max-w-full overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-xs text-slate-100 dark:bg-slate-950"
      {...props}
    >
      {children}
    </pre>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote
      className="my-1.5 border-l-2 border-brand-border pl-3 italic text-brand-text-muted dark:border-slate-700"
      {...props}
    >
      {children}
    </blockquote>
  ),
  hr: (props) => <hr className="my-2 border-brand-border dark:border-slate-700" {...props} />,
  table: ({ children, ...props }) => (
    <div className="my-2.5 max-w-full overflow-x-auto rounded-lg border border-brand-border dark:border-slate-700">
      <table className="min-w-full divide-y divide-brand-border text-left text-xs dark:divide-slate-700" {...props}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="bg-slate-50 dark:bg-slate-800/80" {...props}>
      {children}
    </thead>
  ),
  tbody: ({ children, ...props }) => (
    <tbody className="divide-y divide-brand-border/60 bg-white dark:divide-slate-700/60 dark:bg-slate-900" {...props}>
      {children}
    </tbody>
  ),
  tr: ({ children, ...props }) => (
    <tr className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors" {...props}>
      {children}
    </tr>
  ),
  th: ({ children, style, ...props }) => (
    <th
      scope="col"
      style={style}
      className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-brand-text dark:text-slate-200"
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ children, style, ...props }) => (
    <td
      style={style}
      className="px-3 py-2 text-xs text-brand-text dark:text-slate-300 align-top"
      {...props}
    >
      {children}
    </td>
  ),
  a: SafeLink,
}

function AssistantMarkdownContent({ content, className = '' }) {
  if (!content) return null

  return (
    <div className={`assistant-markdown-content text-sm leading-relaxed ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default memo(AssistantMarkdownContent)
