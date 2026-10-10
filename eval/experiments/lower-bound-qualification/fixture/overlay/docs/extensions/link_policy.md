title: Link Policy Extension

# Link Policy

## Summary

The Link Policy extension neutralizes links whose URL scheme a site does not allow, such as `javascript:` links
in user-submitted text. A blocked link keeps its text: its `href` attribute is removed and it is marked with
`data-link-policy="blocked"`.

## Usage

See the extensions index for general extension usage. Use `markdown.extensions.linkpolicy` as the name of the
extension.

```python
>>> import markdown
>>> markdown.markdown('[home](https://example.com/) [x](javascript:alert)',
...                   extensions=['markdown.extensions.linkpolicy'])
'<p><a href="https://example.com/">home</a> <a data-link-policy="blocked">x</a></p>'
```

### Options

The following options are provided to configure the output:

| Option | Default | Description |
|--------|---------|-------------|
| `blocked_schemes` | `['javascript', 'vbscript', 'data']` | URL schemes whose links are neutralized. A comma-separated string is accepted too. |
| `allow_relative` | `True` | Keep links without a scheme (relative links). When `False`, they are neutralized as well. |
| `internal_hosts` | `[]` | Hosts that are the site's own. Links to them are internal. |
| `strict` | `False` | Raise `LinkPolicyError` at a blocked link instead of neutralizing it. |

```python
markdown.markdown(text, extensions=['markdown.extensions.linkpolicy'],
                  extension_configs={'markdown.extensions.linkpolicy': {'allow_relative': False}})
```
