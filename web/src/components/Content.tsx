import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
export function SafeContent({
  format,
  text,
}: {
  format: string;
  text: string;
}) {
  if (format !== 'markdown')
    return (
      <div className="prose">
        <p>
          {format !== 'plain' && (
            <strong>Unknown content format: {format}. </strong>
          )}
          {text}
        </p>
      </div>
    );
  return (
    <div className="prose">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        disallowedElements={['img']}
        components={{
          a: ({ href, children }) => {
            if (!href) return <span>{children}</span>;
            // Only explicit HTTPS/HTTP external navigation or same-origin relative links.
            if (/^https?:\/\//i.test(href))
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Opens an external website"
                >
                  {children} <small>(external)</small>
                </a>
              );
            if (
              (href.startsWith('/') && !href.startsWith('//')) ||
              href.startsWith('#')
            )
              return <a href={href}>{children}</a>;
            return <span>{children}</span>;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
export function JsonContent({ value }: { value: unknown }) {
  return (
    <pre>
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  );
}
