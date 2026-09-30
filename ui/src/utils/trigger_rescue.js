export const rescue_condition_expression = 'op_data.rescue_needed()'

export const rescue_condition_help =
  '至少两名且半数可轮休主表主班低于各自救急线时进入，直到多数主班达到主表心情上限后退出。救急期间主表主班与主表高优替补的休息优先级最高；救急副表显式安排的工作干员默认 0 心情工作，无需填写替班，禁止进入宿舍。宿舍黑名单仍生效，不清空宿舍，仅使用现有 Free 床位。未配置此条件时保留原救急安排。'

export function rescue_trigger() {
  return { left: rescue_condition_expression, operator: '==', right: 'True' }
}
