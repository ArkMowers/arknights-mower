export const facility_type_names = ['贸易站', '制造站', '发电站']

export const plan_facility_type_options = facility_type_names.map((name) => ({
  label: name,
  value: name
}))

export const trigger_facility_type_options = facility_type_names.map((name) => ({
  label: name,
  value: `'${name}'`
}))
