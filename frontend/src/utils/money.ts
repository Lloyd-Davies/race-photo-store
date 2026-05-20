export function formatMoney(pence: number | undefined, currency = 'GBP') {
  const amount = (pence ?? 0) / 100
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
  }).format(amount)
}
