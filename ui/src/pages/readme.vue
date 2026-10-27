<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import PageLayout from '@/components/PageLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

defineOptions({ name: 'ResourceLinksPage' })
</script>

<template>
  <PageLayout>
    <template #header>
      <PageHeader>{{ t('reference.linksTitle') }}</PageHeader>
    </template>
    <div>
      <h2 id="mower">Mower</h2>
      <p>
        {{ t('reference.introOld')
        }}<n-a target="_blank" href="https://www.bilibili.com/video/BV1KT411s7Ar">BV1KT411s7Ar</n-a>
      </p>
      <p>
        {{ t('reference.planTutorialOld')
        }}<n-a target="_blank" href="https://www.bilibili.com/video/BV1UM4y1y7bA">BV1UM4y1y7bA</n-a>
      </p>
      <p>{{ t('reference.customPlanOld') }}</p>
      <ul>
        <li>
          {{ t('reference.redpine') }}（<n-a
            target="_blank"
            href="https://www.bilibili.com/video/BV1oC4y1U7bo"
            >BV1oC4y1U7bo</n-a
          >）
        </li>
        <li>
          跃跃（<n-a target="_blank" href="https://www.bilibili.com/video/BV1Bz4y1w7mj"
            >BV1Bz4y1w7mj</n-a
          >）
        </li>
        <li>
          {{ t('reference.automation') }}（<n-a
            target="_blank"
            href="https://www.bilibili.com/video/BV1Uw411N7WJ"
            >BV1Uw411N7WJ</n-a
          >）
        </li>
      </ul>
      <p>
        {{ t('reference.onlineDocs')
        }}<n-a target="_blank" href="https://arkmowers.github.io/arknights-mower/"
          >https://arkmowers.github.io/arknights-mower/</n-a
        >
      </p>
      <p>
        {{ t('reference.sourceCode')
        }}<n-a target="_blank" href="https://github.com/ArkMowers/arknights-mower"
          >https://github.com/ArkMowers/arknights-mower</n-a
        >
      </p>
      <p>
        {{ t('reference.tutorialWip')
        }}<n-a target="_blank" href="https://blog.zhaozuohong.vip/categories/arknights-mower/"
          >https://blog.zhaozuohong.vip/categories/arknights-mower/</n-a
        >
      </p>
      <p>
        {{ t('reference.runSource')
        }}<n-a
          target="_blank"
          href="https://blog.zhaozuohong.vip/2023/08/02/run-arknights-mower-from-source/"
          >https://blog.zhaozuohong.vip/2023/08/02/run-arknights-mower-from-source/</n-a
        >
      </p>
      <p>{{ t('reference.installation') }}</p>
      <ul>
        <li>
          {{ t('reference.newUpdater')
          }}<n-a target="_blank" href="https://github.com/Funny-ppt/MowerUpdater"
            >https://github.com/Funny-ppt/MowerUpdater</n-a
          >）
        </li>
        <li>
          {{ t('reference.oldUpdater')
          }}<n-a target="_blank" href="https://github.com/ArkMowers/updater"
            >https://github.com/ArkMowers/updater</n-a
          >）
        </li>
        <li>
          {{ t('reference.actionsBuild')
          }}<n-a target="_blank" href="https://github.com/ArkMowers/arknights-mower/actions"
            >https://github.com/ArkMowers/arknights-mower/actions</n-a
          >
        </li>
        <li>
          {{ t('reference.releaseDownload')
          }}<n-a target="_blank" href="https://github.com/ArkMowers/arknights-mower/releases"
            >https://github.com/ArkMowers/arknights-mower/releases</n-a
          >
        </li>
        <li>
          {{ t('reference.directDownloadPrefix') }}
          <n-a target="_blank" href="https://mower.zhaozuohong.vip/"
            >https://mower.zhaozuohong.vip</n-a
          >
          {{ t('reference.getDownload') }}
        </li>
      </ul>
    </div>
    <div>
      <h2 id="mower0">Mower0</h2>
      <p>
        {{ t('reference.intro')
        }}<n-a target="_blank" href="https://www.bilibili.com/video/BV1qu4y1k7AX">BV1qu4y1k7AX</n-a>
      </p>
      <p>
        {{ t('reference.sourceCode')
        }}<n-a target="_blank" href="https://github.com/Bidgecfah/Mower0"
          >https://github.com/Bidgecfah/Mower0</n-a
        >
      </p>
      <p>{{ t('reference.groupDownload') }}</p>
    </div>

    <div>
      <h2 id="其它资源">{{ t('reference.otherResources') }}</h2>
      <p>
        {{ t('reference.prices')
        }}<n-a target="_blank" href="https://github.com/Bidgecfah/Rhodes-Island-Bureau-of-Price"
          >https://github.com/Bidgecfah/Rhodes-Island-Bureau-of-Price</n-a
        >
      </p>
      <p>{{ t('reference.baseSimulator') }}</p>
      <ul>
        <li>
          {{ t('reference.useOnline')
          }}<n-a target="_blank" href="https://infrastsim.zhaozuohong.vip/"
            >https://infrastsim.zhaozuohong.vip</n-a
          >）
        </li>
        <li>
          {{ t('reference.projectSource')
          }}<n-a target="_blank" href="https://github.com/Funny-ppt/InfrastSim"
            >https://github.com/Funny-ppt/InfrastSim</n-a
          >）
        </li>
        <li>
          {{ t('reference.frontendSource')
          }}<n-a target="_blank" href="https://github.com/Funny-ppt/InfrastSimUI"
            >https://github.com/Funny-ppt/InfrastSimUI</n-a
          >）
        </li>
      </ul>
      <p>
        {{ t('reference.arknTools')
        }}<n-a target="_blank" href="https://arkntools.app/">https://arkn.lolicon.app</n-a>
      </p>
      <p>MAA：<n-a target="_blank" href="https://maa.plus/">https://maa.plus/</n-a></p>
      <p>
        {{ t('reference.priceTheory')
        }}<n-a
          target="_blank"
          href="https://bidgecfah.gitee.io/2023/07/12/%E6%98%8E%E6%97%A5%E6%96%B9%E8%88%9F%E5%AE%9A%E4%BB%B7%E7%90%86%E8%AE%BA/"
          >https://bidgecfah.gitee.io/2023/07/12/%E6%98%8E%E6%97%A5%E6%96%B9%E8%88%9F%E5%AE%9A%E4%BB%B7%E7%90%86%E8%AE%BA/</n-a
        >
      </p>
    </div>
  </PageLayout>
</template>

<style scoped>
.page-content {
  word-break: break-all;
}
</style>
