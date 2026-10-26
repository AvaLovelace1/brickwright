/** Memoizes an async load by key. A failed load is forgotten, so the next call retries it. */
export function cached<T>(load: (key: string) => Promise<T>): (key: string) => Promise<T> {
  const results = new Map<string, Promise<T>>();
  return (key) => {
    let result = results.get(key);
    if (!result) {
      result = load(key).catch((error) => {
        results.delete(key);
        throw error;
      });
      results.set(key, result);
    }
    return result;
  };
}
