/** Tiny clsx-like helper — avoids adding the clsx package for just this usage */
export function clsx(...classes: (string | undefined | null | false)[]) {
  return classes.filter(Boolean).join(' ')
}
