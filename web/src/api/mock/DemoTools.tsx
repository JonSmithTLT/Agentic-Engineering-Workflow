import { selectedWorld, worlds } from './worlds';
export default function DemoTools() {
  return (
    <label className="world-picker">
      Demo scenario
      <select
        value={selectedWorld().fixture}
        onChange={(e) => {
          const url = new URL(location.href);
          url.searchParams.set('fixture', e.target.value);
          url.searchParams.delete('cursor');
          location.assign(url);
        }}
      >
        {worlds.map((w) => (
          <option key={w.fixture} value={w.fixture}>
            {w.fixture} · {w.name}
          </option>
        ))}
      </select>
    </label>
  );
}
