import { expect, it } from 'vitest'
import { certificateRewards, createCertificateValuation } from './incomeCertificates'
import { createIncomeSanityValuation, validateIncomeSanityValuation } from './incomeSanity'

const valuation = () => ({ prices: { 合成玉: 0.9225, 采购凭证: 1.5 } })
it('uses final material prices for both yellow presets and green certificates without draw returns', () => {
  const first = createCertificateValuation(valuation())
  expect(first.yellow).toBeCloseTo(81.52325581395348)
  expect(first.green).toBe(0.5535)
  expect(first.orundum).toBe(0.9225)
  const token = createCertificateValuation({
    ...valuation(),
    income_options: { yellow_preset: 'royal_token' }
  })
  expect(token.yellow).toBe(8)
  expect(token.green).toBe(0.5535)
})
it('values only the improvement over a three-star outcome using consistent survey category totals', () => {
  const result = createCertificateValuation(valuation())
  const total = 706822982
  expect(result.refreshYellow).toBeCloseTo((108025329 + 5 * 3878075 + 10 * 1511907) / total)
  expect(result.refreshGreen).toBeCloseTo((20 * 108025329 - 10 * 3878075 - 10 * 1511907) / total)
  const full = createCertificateValuation({
    ...valuation(),
    income_options: { potential_preset: 'full' }
  })
  expect(full.refreshYellow).toBeCloseTo((108025329 + 13 * 3878075 + 25 * 1511907) / total)
  expect(full.refreshGreen).toBe(result.refreshGreen)
})
it('estimates current ownership and potentials per public-recruitment rarity and leaves missing data unknown', () => {
  const roster = [
    { stars: 3, owned: true, potential: 6 },
    { stars: 4, owned: true, potential: 5 },
    { stars: 4, owned: true, potential: 6 },
    { stars: 5, owned: false, potential: null },
    { stars: 5, owned: true, potential: 6 },
    { stars: 6, owned: true, potential: 6 }
  ]
  expect(certificateRewards('skland', roster)).toEqual({
    3: { yellow: 0, green: 10 },
    4: { yellow: 0.5, green: 30 },
    5: { yellow: 7, green: 0 },
    6: { yellow: 25, green: 0 }
  })
  roster[1].potential = null
  expect(certificateRewards('skland', roster)).toBeNull()
  expect(certificateRewards('skland', null)).toBeNull()
  expect(
    createCertificateValuation({ ...valuation(), income_options: { potential_preset: 'skland' } })
      .recruitmentValue
  ).toBeNull()
})
it('keeps explicit zero overrides, independent choices and missing material values', () => {
  const result = createCertificateValuation({
    ...valuation(),
    income_unit_values: {
      yellow_certificate: 0,
      green_certificate: 0,
      recruitment_certificates: 0.7
    }
  })
  expect(result.refreshYellow).toBe(0.7)
  expect(result.recruitmentValue).toBe(0)
  expect(createCertificateValuation({ prices: {} }).yellow).toBeNull()
  expect(createCertificateValuation({ prices: {} }).green).toBeNull()
})
it('retains negative marginal certificate value instead of discarding lost green certificates', () => {
  const roster = [
    { stars: 3, owned: true, potential: 6 },
    ...[4, 5, 6].map((stars) => ({ stars, owned: false, potential: null }))
  ]
  const snapshot = createIncomeSanityValuation(
    {
      ...valuation(),
      income_options: { potential_preset: 'skland' },
      income_unit_values: { yellow_certificate: 0 }
    },
    roster
  )
  expect(snapshot.unitValues.recruitment).toBeLessThan(0)
  expect(() => validateIncomeSanityValuation(snapshot)).not.toThrow()
})
