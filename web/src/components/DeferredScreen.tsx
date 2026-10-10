import { Component, Suspense, lazy, type ComponentType, type ReactNode } from 'react';

class ScreenFailure extends Component<{ children: ReactNode; name: string }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <div role="alert" className="empty">
        <p>{this.props.name} could not open. Reload the page to try again with the same link.</p>
        <button onClick={() => window.location.reload()}>Reload page</button>
      </div>;
    }
    return this.props.children;
  }
}

// Define once, outside rendering: changing selections must not remount the screen.
export function deferredScreen<P extends object>(
  name: string,
  load: () => Promise<{ default: ComponentType<P> }>,
): ComponentType<P> {
  const Screen = lazy(load);
  return function DeferredScreen(props: P) {
    return <ScreenFailure name={name}>
      <Suspense fallback={<p role="status">Opening {name}…</p>}>
        <Screen {...props} />
      </Suspense>
    </ScreenFailure>;
  };
}
