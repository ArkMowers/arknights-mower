export function swap(source, target, arr) {
  const source_plan = arr[source]
  arr[source] = arr[target]
  arr[target] = source_plan
}
