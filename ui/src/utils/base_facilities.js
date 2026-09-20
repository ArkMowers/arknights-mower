export const facility_types = [
  { label: '贸易站', value: 'trade' },
  { label: '制造站', value: 'factory' },
  { label: '发电站', value: 'power' }
]

export const plan_facility_type_options = facility_types.map(({ label }) => ({
  label,
  value: label
}))

export const trigger_facility_type_options = facility_types
