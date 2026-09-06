const transparentBorder = '1px solid transparent'

const sharedCommon = {
  borderRadius: '6px',
  borderRadiusSmall: '4px',
  fontWeightStrong: '600'
}

function createMowerTheme(palette) {
  // shadcn `outline` 变体的默认按钮：给普通（无 type）按钮 1px 可见边框，
  // 让它不再是无边框的浅灰平铺块。primary 系列保留透明边框（实心绿不要边）。
  const defaultBorder = `1px solid ${palette.border}`
  return {
    common: {
      ...sharedCommon,
      primaryColor: palette.primary,
      primaryColorHover: palette.primaryHover,
      primaryColorPressed: palette.primaryPressed,
      primaryColorSuppl: palette.primarySuppl,
      successColor: palette.success,
      successColorHover: palette.successHover,
      successColorPressed: palette.successPressed,
      successColorSuppl: palette.successSuppl,
      warningColor: palette.warning,
      warningColorHover: palette.warningHover,
      warningColorPressed: palette.warningPressed,
      warningColorSuppl: palette.warningSuppl,
      errorColor: palette.error,
      errorColorHover: palette.errorHover,
      errorColorPressed: palette.errorPressed,
      errorColorSuppl: palette.errorSuppl,
      infoColor: palette.info,
      infoColorHover: palette.infoHover,
      infoColorPressed: palette.infoPressed,
      infoColorSuppl: palette.infoSuppl,
      bodyColor: palette.page,
      cardColor: palette.surface,
      modalColor: palette.surfaceRaised,
      popoverColor: palette.popover,
      inputColor: palette.input,
      actionColor: palette.control,
      hoverColor: palette.controlHover,
      pressedColor: palette.controlPressed,
      borderColor: palette.border,
      dividerColor: palette.divider,
      tableColor: palette.surface,
      tableHeaderColor: palette.tableHeader,
      tableColorStriped: palette.tableStriped,
      tabColor: palette.tab,
      boxShadow1: palette.shadowSmall,
      boxShadow2: palette.shadowMedium,
      boxShadow3: palette.shadowLarge
    },
    Layout: {
      color: palette.page,
      colorEmbedded: palette.control,
      headerColor: palette.surface,
      siderColor: palette.sider,
      footerColor: palette.surface,
      headerBorderColor: 'transparent',
      siderBorderColor: 'transparent',
      footerBorderColor: 'transparent'
    },
    Button: {
      borderRadiusTiny: '3px',
      borderRadiusSmall: '4px',
      borderRadiusMedium: '6px',
      borderRadiusLarge: '8px',
      border: defaultBorder,
      borderFocus: defaultBorder,
      borderHover: defaultBorder,
      borderPressed: defaultBorder,
      borderDisabled: defaultBorder,
      color: palette.control,
      colorFocus: palette.controlHover,
      colorHover: palette.controlHover,
      colorPressed: palette.controlPressed,
      borderPrimary: transparentBorder,
      borderFocusPrimary: transparentBorder,
      borderHoverPrimary: transparentBorder,
      borderPressedPrimary: transparentBorder,
      colorPrimary: palette.accent,
      colorFocusPrimary: palette.accentHover,
      colorHoverPrimary: palette.accentHover,
      colorPressedPrimary: palette.accentPressed,
      rippleColorPrimary: palette.accentPressed,
      textColorPrimary: palette.accentText,
      textColorFocusPrimary: palette.accentText,
      textColorHoverPrimary: palette.accentText,
      textColorPressedPrimary: palette.accentText
    },
    Card: {
      color: palette.cardBlock,
      colorEmbedded: palette.control,
      actionColor: palette.control,
      borderColor: 'transparent',
      borderRadius: '12px',
      closeBorderRadius: '6px',
      boxShadow: 'none'
    },
    Dialog: {
      border: transparentBorder,
      borderRadius: '12px',
      closeBorderRadius: '6px',
      color: palette.surfaceRaised
    },
    Modal: {
      boxShadow: palette.shadowLarge
    },
    Drawer: {
      borderRadius: '12px',
      closeBorderRadius: '6px',
      boxShadow: palette.shadowLarge
    },
    Input: {
      border: transparentBorder,
      borderDisabled: transparentBorder,
      borderFocus: transparentBorder,
      borderHover: transparentBorder,
      borderRadius: '6px',
      boxShadowFocus: palette.focusShadow,
      color: palette.control,
      colorDisabled: palette.controlDisabled,
      colorFocus: palette.controlFocus,
      caretColor: palette.primary
    },
    Checkbox: {
      border: transparentBorder,
      borderChecked: transparentBorder,
      borderDisabled: transparentBorder,
      borderDisabledChecked: transparentBorder,
      borderFocus: transparentBorder,
      boxShadowFocus: palette.focusShadow,
      borderRadius: '3px',
      color: palette.control,
      colorChecked: palette.accent,
      colorDisabled: palette.controlDisabled,
      colorDisabledChecked: palette.controlDisabled,
      checkMarkColor: palette.accentText
    },
    Radio: {
      buttonBorderRadius: '6px',
      color: palette.control,
      colorActive: palette.accent,
      dotColorActive: palette.accentText,
      boxShadow: `inset 0 0 0 1px ${palette.border}`,
      boxShadowHover: `inset 0 0 0 1px ${palette.primary}`,
      boxShadowActive: 'none',
      boxShadowFocus: palette.focusShadow
    },
    Switch: {
      railBorderRadiusSmall: '9px',
      railBorderRadiusMedium: '11px',
      railBorderRadiusLarge: '13px',
      buttonBorderRadiusSmall: '7px',
      buttonBorderRadiusMedium: '9px',
      buttonBorderRadiusLarge: '11px',
      railColor: palette.controlPressed,
      railColorActive: palette.accent,
      buttonColor: palette.surfaceRaised,
      buttonBoxShadow: 'none',
      boxShadowFocus: palette.focusShadow,
      textColor: palette.accentText
    },
    Select: {
      menuBoxShadow: palette.shadowMedium
    },
    AutoComplete: {
      menuBoxShadow: palette.shadowMedium
    },
    Tag: {
      border: transparentBorder,
      borderPrimary: transparentBorder,
      borderSuccess: transparentBorder,
      borderWarning: transparentBorder,
      borderError: transparentBorder,
      borderInfo: transparentBorder,
      borderRadius: '3px',
      closeBorderRadius: '3px',
      color: palette.control,
      colorBordered: palette.control,
      colorPrimary: palette.primaryBlock,
      colorBorderedPrimary: palette.primaryBlock,
      colorSuccess: palette.successBlock,
      colorBorderedSuccess: palette.successBlock,
      colorWarning: palette.warningBlock,
      colorBorderedWarning: palette.warningBlock,
      colorError: palette.errorBlock,
      colorBorderedError: palette.errorBlock,
      colorInfo: palette.infoBlock,
      colorBorderedInfo: palette.infoBlock,
      textColorPrimary: palette.primaryText,
      textColorSuccess: palette.successText,
      textColorWarning: palette.warningText,
      textColorError: palette.errorText,
      textColorInfo: palette.infoText
    },
    Menu: {
      borderRadius: '6px',
      itemColorActive: palette.primaryBlock,
      itemColorActiveCollapsed: palette.primaryBlock,
      itemColorActiveHover: palette.primaryBlock
    },
    Popover: {
      color: palette.popover,
      borderRadius: '10px',
      boxShadow: palette.shadowMedium
    },
    Dropdown: {
      borderRadius: '8px',
      color: palette.popover,
      dividerColor: palette.divider
    },
    Tooltip: {
      borderRadius: '6px',
      boxShadow: palette.shadowSmall,
      color: palette.tooltip,
      textColor: palette.tooltipText,
      peers: {
        Popover: {
          borderRadius: '6px',
          boxShadow: palette.shadowSmall,
          color: palette.tooltip,
          textColor: palette.tooltipText
        }
      }
    },
    Message: {
      borderRadius: '8px',
      closeBorderRadius: '5px',
      boxShadow: palette.shadowMedium,
      boxShadowInfo: palette.shadowMedium,
      boxShadowSuccess: palette.shadowMedium,
      boxShadowWarning: palette.shadowMedium,
      boxShadowError: palette.shadowMedium,
      boxShadowLoading: palette.shadowMedium
    },
    Notification: {
      borderRadius: '10px',
      closeBorderRadius: '5px',
      boxShadow: palette.shadowMedium
    },
    Alert: {
      border: transparentBorder,
      borderInfo: transparentBorder,
      borderSuccess: transparentBorder,
      borderWarning: transparentBorder,
      borderError: transparentBorder,
      borderRadius: '8px',
      closeBorderRadius: '5px',
      color: palette.control,
      colorInfo: palette.alertInfoBlock,
      colorSuccess: palette.alertSuccessBlock,
      colorWarning: palette.alertWarningBlock,
      colorError: palette.alertErrorBlock,
      iconColorInfo: palette.alertInfoIcon,
      iconColorSuccess: palette.alertSuccessIcon,
      iconColorWarning: palette.alertWarningIcon,
      iconColorError: palette.alertErrorIcon
    },
    Divider: {
      color: palette.divider
    },
    Collapse: {
      dividerColor: 'transparent',
      titleFontWeight: '600'
    },
    DataTable: {
      borderRadius: '10px',
      borderColor: palette.divider,
      thColor: palette.tableHeader,
      tdColor: palette.surface,
      tdColorStriped: palette.tableStriped
    },
    DatePicker: {
      itemBorderRadius: '4px',
      scrollItemBorderRadius: '4px',
      panelBorderRadius: '10px',
      panelBoxShadow: palette.shadowMedium,
      panelColor: palette.surfaceRaised,
      panelHeaderDividerColor: palette.divider,
      calendarDaysDividerColor: palette.divider,
      calendarDividerColor: palette.divider,
      panelActionDividerColor: palette.divider
    },
    List: {
      borderRadius: '10px',
      borderColor: palette.divider,
      color: palette.surface,
      colorHover: palette.controlHover
    },
    Slider: {
      /* 亮色下白色 thumb 会融进白色轨道/背景，给一圈极淡描边+柔和投影分离轮廓（不改颜色） */
      handleBoxShadow: '0 0 0 1px rgba(0, 0, 0, 0.12), 0 1px 3px rgba(0, 0, 0, 0.14)',
      handleBoxShadowFocus: palette.focusShadow,
      indicatorBorderRadius: '6px',
      indicatorBoxShadow: palette.shadowSmall
    },
    Table: {
      borderRadius: '10px',
      borderColor: palette.divider,
      thColor: palette.tableHeader,
      tdColor: palette.surface,
      tdColorStriped: palette.tableStriped
    },
    Tabs: {
      tabBorderRadius: '6px',
      closeBorderRadius: '4px',
      tabColor: palette.control,
      tabColorSegment: palette.surfaceRaised,
      colorSegment: palette.controlPressed
    },
    TimePicker: {
      itemBorderRadius: '4px',
      borderRadius: '10px',
      panelBoxShadow: palette.shadowMedium,
      panelColor: palette.surfaceRaised,
      panelDividerColor: palette.divider
    },
    Upload: {
      borderRadius: '8px',
      draggerColor: palette.control,
      draggerBorder: transparentBorder,
      draggerBorderHover: transparentBorder,
      itemColorHover: palette.controlHover
    }
  }
}

export const mowerLightThemeOverrides = createMowerTheme({
  primary: '#18a058',
  primaryHover: '#36ad6a',
  primaryPressed: '#0c7a43',
  primarySuppl: '#36ad6a',
  accent: '#18a058',
  accentHover: '#36ad6a',
  accentPressed: '#0c7a43',
  accentText: '#ffffff',
  success: '#18a058',
  successHover: '#36ad6a',
  successPressed: '#0c7a43',
  successSuppl: '#36ad6a',
  warning: '#f0a020',
  warningHover: '#fcb040',
  warningPressed: '#c97c10',
  warningSuppl: '#fcb040',
  error: '#d03050',
  errorHover: '#de576d',
  errorPressed: '#ab1f3f',
  errorSuppl: '#de576d',
  info: '#2080f0',
  infoHover: '#4098fc',
  infoPressed: '#1060c9',
  infoSuppl: '#4098fc',
  page: '#fff',
  surface: '#fff',
  surfaceRaised: '#fff',
  popover: '#fff',
  tooltip: 'rgba(0, 0, 0, 0.85)',
  tooltipText: '#ffffff',
  input: 'rgba(255, 255, 255, 1)',
  sider: 'rgb(250, 250, 252)',
  cardBlock: '#ffffff',
  control: 'rgb(250, 250, 252)',
  controlHover: 'rgb(243, 243, 245)',
  controlPressed: 'rgb(237, 237, 239)',
  controlFocus: '#ffffff',
  controlDisabled: 'rgb(250, 250, 252)',
  border: 'rgb(224, 224, 230)',
  divider: 'rgb(239, 239, 245)',
  tableHeader: 'rgb(250, 250, 252)',
  tableStriped: 'rgba(0, 0, 100, 0.02)',
  tab: 'rgb(247, 247, 250)',
  primaryBlock: 'rgba(24, 160, 88, 0.12)',
  primaryText: '#18a058',
  successBlock: 'rgba(24, 160, 88, 0.12)',
  successText: '#18a058',
  warningBlock: 'rgba(240, 160, 32, 0.15)',
  warningText: '#f0a020',
  errorBlock: 'rgba(208, 48, 80, 0.1)',
  errorText: '#d03050',
  infoBlock: 'rgba(32, 128, 240, 0.12)',
  infoText: '#2080f0',
  alertInfoBlock: 'rgba(237, 245, 254, 1)',
  alertSuccessBlock: 'rgba(237, 247, 242, 1)',
  alertWarningBlock: 'rgba(254, 247, 237, 1)',
  alertErrorBlock: 'rgba(251, 238, 241, 1)',
  alertInfoIcon: '#2080f0',
  alertSuccessIcon: '#18a058',
  alertWarningIcon: '#f0a020',
  alertErrorIcon: '#d03050',
  focusShadow: '0 0 0 2px rgba(24, 160, 88, 0.2)',
  switchShadow: '0 1px 3px rgba(0, 0, 0, 0.12)',
  shadowSmall:
    '0 1px 2px -2px rgba(0, 0, 0, .08), 0 3px 6px 0 rgba(0, 0, 0, .06), 0 5px 12px 4px rgba(0, 0, 0, .04)',
  shadowMedium:
    '0 3px 6px -4px rgba(0, 0, 0, .12), 0 6px 16px 0 rgba(0, 0, 0, .08), 0 9px 28px 8px rgba(0, 0, 0, .05)',
  shadowLarge:
    '0 6px 16px -9px rgba(0, 0, 0, .08), 0 9px 28px 0 rgba(0, 0, 0, .05), 0 12px 48px 16px rgba(0, 0, 0, .03)'
})

export const mowerDarkThemeOverrides = createMowerTheme({
  primary: '#63e2b7',
  primaryHover: '#7fe7c4',
  primaryPressed: '#5acea7',
  primarySuppl: 'rgb(42, 148, 125)',
  accent: '#63e2b7',
  accentHover: '#7fe7c4',
  accentPressed: '#5acea7',
  accentText: '#000000',
  success: '#63e2b7',
  successHover: '#7fe7c4',
  successPressed: '#5acea7',
  successSuppl: 'rgb(42, 148, 125)',
  warning: '#f2c97d',
  warningHover: '#f5d599',
  warningPressed: '#e6c260',
  warningSuppl: 'rgb(240, 138, 0)',
  error: '#e88080',
  errorHover: '#e98b8b',
  errorPressed: '#e57272',
  errorSuppl: 'rgb(208, 58, 82)',
  info: '#70c0e8',
  infoHover: '#8acbec',
  infoPressed: '#66afd3',
  infoSuppl: 'rgb(56, 137, 197)',
  page: 'rgb(16, 16, 20)',
  surface: 'rgb(24, 24, 28)',
  surfaceRaised: 'rgb(44, 44, 50)',
  popover: 'rgb(72, 72, 78)',
  tooltip: 'rgb(72, 72, 78)',
  tooltipText: 'rgba(255, 255, 255, 0.9)',
  input: 'rgba(255, 255, 255, 0.1)',
  sider: 'rgb(24, 24, 28)',
  cardBlock: 'rgb(24, 24, 28)',
  control: 'rgba(255, 255, 255, 0.06)',
  controlHover: 'rgba(255, 255, 255, 0.09)',
  controlPressed: 'rgba(255, 255, 255, 0.05)',
  controlFocus: 'rgba(255, 255, 255, 0.1)',
  controlDisabled: 'rgba(255, 255, 255, 0.06)',
  border: 'rgba(255, 255, 255, 0.24)',
  divider: 'rgba(255, 255, 255, 0.09)',
  tableHeader: 'rgba(255, 255, 255, 0.06)',
  tableStriped: 'rgba(255, 255, 255, 0.05)',
  tab: 'rgba(255, 255, 255, 0.04)',
  primaryBlock: 'rgba(99, 226, 183, 0.16)',
  primaryText: '#63e2b7',
  successBlock: 'rgba(99, 226, 183, 0.16)',
  successText: '#63e2b7',
  warningBlock: 'rgba(242, 201, 125, 0.16)',
  warningText: '#f2c97d',
  errorBlock: 'rgba(232, 128, 128, 0.16)',
  errorText: '#e88080',
  infoBlock: 'rgba(112, 192, 232, 0.16)',
  infoText: '#70c0e8',
  alertInfoBlock: 'rgba(56, 137, 197, 0.25)',
  alertSuccessBlock: 'rgba(42, 148, 125, 0.25)',
  alertWarningBlock: 'rgba(240, 138, 0, 0.25)',
  alertErrorBlock: 'rgba(208, 58, 82, 0.25)',
  alertInfoIcon: 'rgb(56, 137, 197)',
  alertSuccessIcon: 'rgb(42, 148, 125)',
  alertWarningIcon: 'rgb(240, 138, 0)',
  alertErrorIcon: 'rgb(208, 58, 82)',
  focusShadow: '0 0 0 2px rgba(99, 226, 183, 0.2)',
  switchShadow: '0 1px 3px rgba(0, 0, 0, 0.24)',
  shadowSmall:
    '0 1px 2px -2px rgba(0, 0, 0, .24), 0 3px 6px 0 rgba(0, 0, 0, .18), 0 5px 12px 4px rgba(0, 0, 0, .12)',
  shadowMedium:
    '0 3px 6px -4px rgba(0, 0, 0, .24), 0 6px 12px 0 rgba(0, 0, 0, .16), 0 9px 18px 8px rgba(0, 0, 0, .10)',
  shadowLarge:
    '0 6px 16px -9px rgba(0, 0, 0, .08), 0 9px 28px 0 rgba(0, 0, 0, .05), 0 12px 48px 16px rgba(0, 0, 0, .03)'
})

function createMowerCssVariables(theme) {
  return {
    '--mower-surface': theme.common.cardColor,
    '--mower-shadow-surface': 'none',
    '--mower-shadow-control': 'none',
    '--mower-control-surface': theme.common.actionColor,
    '--mower-control-hover': theme.common.hoverColor,
    '--mower-divider': theme.common.dividerColor,
    '--mower-primary': theme.common.primaryColor,
    '--mower-primary-hover': theme.common.primaryColorHover,
    '--mower-primary-contrast': theme.Button.textColorPrimary,
    '--mower-primary-block': theme.Tag.colorPrimary,
    '--mower-primary-text': theme.Tag.textColorPrimary,
    '--mower-success': theme.common.successColor,
    '--mower-success-block': theme.Tag.colorSuccess,
    '--mower-success-text': theme.Tag.textColorSuccess,
    '--mower-warning': theme.common.warningColor,
    '--mower-warning-block': theme.Tag.colorWarning,
    '--mower-warning-text': theme.Tag.textColorWarning,
    '--mower-error': theme.common.errorColor,
    '--mower-error-block': theme.Tag.colorError,
    '--mower-error-text': theme.Tag.textColorError,
    '--mower-info': theme.common.infoColor,
    '--mower-info-block': theme.Tag.colorInfo,
    '--mower-info-text': theme.Tag.textColorInfo
  }
}

export const mowerLightCssVariables = createMowerCssVariables(mowerLightThemeOverrides)
export const mowerDarkCssVariables = createMowerCssVariables(mowerDarkThemeOverrides)
