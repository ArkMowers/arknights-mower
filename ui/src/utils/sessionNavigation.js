export function sessionLocation(to, from) {
  if (!from.query.token || to.query.token) return to
  return {
    path: to.path,
    query: { ...from.query, ...to.query },
    hash: to.hash
  }
}
