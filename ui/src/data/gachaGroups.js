// 初始编组可直接编辑；仅保留必要的技能数值说明。
export const builtinGroups = [
  {
    "id": "builtin-smoke",
    "title": "人间烟火",
    "core": [
      "char_2014_nian",
      "char_2015_dusk",
      "char_2023_ling",
      "char_2025_shu",
      "char_2024_chyue"
    ],
    "support": [
      "char_455_nothin",
      "char_391_rosmon",
      "char_436_whispr"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "通用"
  },
  {
    "id": "builtin-automation",
    "title": "清流·自动化",
    "core": [
      "char_385_finlpp",
      "char_416_zumama",
      "char_400_weedy"
    ],
    "support": [
      "char_1027_greyy2",
      "char_472_pasngr",
      "char_285_medic2"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "金属"
  },
  {
    "id": "builtin-abyss",
    "title": "深海猎人",
    "core": [
      "char_474_glady",
      "char_263_skadi",
      "char_143_ghost",
      "char_1023_ghost2",
      "char_4145_ulpia"
    ],
    "support": [
      "char_218_cuttle"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "通用"
  },
  {
    "id": "builtin-redpine",
    "title": "红松林",
    "core": [
      "char_420_flamtl",
      "char_430_fartth",
      "char_431_ashlok",
      "char_496_wildmn"
    ],
    "support": [
      "char_4000_jnight"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "金属"
  },
  {
    "id": "builtin-tianmao",
    "title": "凯尔希·思衡托",
    "core": [
      "char_1052_kalts2"
    ],
    "support": [
      "char_391_rosmon",
      "char_017_huang",
      "char_4133_logos",
      "char_1040_blaze2",
      "char_4195_radian",
      "char_4204_mantra",
      "char_4230_mcnist"
    ],
    "note": "精二：办公室联络+30%；其他设施每间额外+4%，最多5间。",
    "kind": "built-in",
    "facility": "办公室"
  },
  {
    "id": "builtin-nasti",
    "title": "娜斯提",
    "core": [
      "char_4212_nasti"
    ],
    "support": [
      "char_108_silent",
      "char_134_ifrit",
      "char_202_demkni",
      "char_128_plosis",
      "char_242_otter",
      "char_248_mgllan",
      "char_4048_doroth",
      "char_135_halo",
      "char_249_mlyss"
    ],
    "note": "精二：每名莱茵生命干员提供贵金属效率+3%，最多5名。",
    "kind": "built-in",
    "facility": "金属"
  },
  {
    "id": "builtin-makoto",
    "title": "结城理·S.E.E.S.",
    "core": [
      "char_4217_makoto",
      "char_4218_aigis",
      "char_4219_yukari"
    ],
    "support": [
      "char_4220_kormr"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "通用"
  },
  {
    "id": "builtin-pozy",
    "title": "鸿雪组",
    "core": [
      "char_4055_bgsnow",
      "char_402_tuye",
      "char_478_kirara"
    ],
    "support": [
      "char_254_vodfox",
      "char_501_durin",
      "char_151_myrtle",
      "char_4054_malist"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "通用"
  },
  {
    "id": "builtin-gold",
    "title": "苍苔金工",
    "core": [
      "char_4106_bryota",
      "char_237_gravel",
      "char_141_nights",
      "char_284_spot"
    ],
    "support": [
      "char_385_finlpp"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "金属"
  },
  {
    "id": "builtin-trade",
    "title": "巫恋贸易",
    "core": [
      "char_254_vodfox",
      "char_486_takila",
      "char_4032_provs"
    ],
    "support": [
      "char_252_bibeak",
      "char_214_kafka"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "贸易"
  },
  {
    "id": "builtin-bubble",
    "title": "泡泡仓库",
    "core": [
      "char_381_bubble",
      "char_163_hpsts"
    ],
    "support": [
      "char_369_bena"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "通用"
  },
  {
    "id": "builtin-cloud",
    "title": "红云仓库",
    "core": [
      "char_190_clour",
      "char_336_folivo"
    ],
    "support": [
      "char_485_pallas",
      "char_2013_cerber"
    ],
    "note": "",
    "kind": "built-in",
    "facility": "通用"
  },
  {
    "id": "builtin-reception-yueyue",
    "title": "跃跃",
    "facility": "会客室",
    "core": [
      "char_4100_caper"
    ],
    "support": [],
    "note": "精一：线索交流时搜集+30%。",
    "kind": "built-in"
  },
  {
    "id": "builtin-reception-executor",
    "title": "见行者",
    "facility": "会客室",
    "core": [
      "char_4036_forcer"
    ],
    "support": [],
    "note": "精二：线索搜集+35%，心情消耗+2/小时。",
    "kind": "built-in"
  },
  {
    "id": "builtin-reception-mixer",
    "title": "信仰搅拌机",
    "facility": "会客室",
    "core": [
      "char_4194_rmixer"
    ],
    "support": [
      "char_300_phenxi"
    ],
    "note": "精二：线索搜集+20%；菲亚梅塔在宿舍时额外+10%。",
    "kind": "built-in"
  },
  {
    "id": "builtin-reception-ines",
    "title": "伊内丝",
    "facility": "会客室",
    "core": [
      "char_4087_ines"
    ],
    "support": [],
    "note": "精二：线索搜集+20%，逐小时提升至+30%。",
    "kind": "built-in"
  }
]
