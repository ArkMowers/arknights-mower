<script setup>
import lantern from '@/assets/halloween/lantern.svg'
import ropeWitch from '@/assets/halloween/rope-witch.png'
import nightingaleWitch from '@/assets/halloween/nightingale-witch.png'
import witchHat from '@/assets/halloween/witch-hat.svg'
import moonBats from '@/assets/halloween/moon-bats.svg'

defineProps({
  kind: { type: String, required: true }
})
</script>

<template>
  <div v-if="kind === 'sidebar'" class="halloween-sidebar" aria-hidden="true">
    <div class="halloween-sidebar__art">
      <svg class="halloween-sidebar__garden" viewBox="0 0 200 48" fill="none">
        <ellipse cx="100" cy="42" rx="78" ry="4" fill="currentColor" opacity=".1" />
        <g stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity=".55">
          <path
            d="M26 42c5-12 3-24-3-35m5 21c4-1 7-5 7-10m-8 18c-7-2-11-7-11-12m150 18c-3-11-1-21 4-30m-5 18c-6-1-8-5-9-10"
          />
          <path
            d="M23 18c-6-3-8-8-6-13 6 4 8 8 6 13Zm7 6c0-6 2-9 6-11 0 7-1 10-6 11ZM19 33c-7-1-10-5-9-10 6 2 10 5 9 10Zm148-9c-1-7 2-11 7-14 1 6-1 11-7 14Z"
            fill="currentColor"
            stroke="none"
          />
        </g>
      </svg>
      <img class="halloween-sidebar__operator" :src="ropeWitch" alt="" draggable="false" />
      <img class="halloween-sidebar__guest" :src="nightingaleWitch" alt="" draggable="false" />
      <img class="halloween-sidebar__pumpkin" :src="lantern" alt="" draggable="false" />
    </div>
    <div class="halloween-sidebar__caption">
      <span class="halloween-sidebar__rule" />
      <span>巫异盛宴</span>
      <span class="halloween-sidebar__rule" />
    </div>
    <span class="halloween-sidebar__subtitle">WITCH FEAST</span>
  </div>
  <div v-else-if="kind === 'titlebar'" class="halloween-title" aria-hidden="true">
    <img :src="moonBats" alt="" draggable="false" />
    <span>巫异盛宴</span>
    <svg class="halloween-title__web" viewBox="0 0 56 36" fill="none">
      <path
        d="M56 0H0m56 0L7 36M56 0 30 36M56 0v36M42 0c0 7 5 12 14 12M27 0c0 8 3 14 9 20 6 5 12 7 20 7M11 0c1 13 6 24 15 32M46 8c-1 7 1 12 5 17M35 17c-2 6-1 13 1 19"
        stroke="currentColor"
        stroke-width=".8"
      />
    </svg>
  </div>
  <span v-else-if="kind === 'wordmark'" class="halloween-wordmark" aria-hidden="true">
    <span
      class="halloween-wordmark__hat"
      :style="{ backgroundImage: 'url(' + JSON.stringify(witchHat) + ')' }"
    />
    <svg class="halloween-wordmark__bat" viewBox="0 0 40 24" fill="none">
      <path
        d="M1 7c5-3 9-2 13 1l3-5 3 4 4-3 1 5c5-1 9 2 14 7-6-1-10 0-12 4-3-2-6-2-9 1-1-4-4-6-8-6-2-4-5-6-9-8Z"
        fill="#89808e"
        stroke="none"
      />
      <path d="m32 1 1 3 3 1-3 1-1 3-1-3-3-1 3-1Z" fill="#c8a16a" stroke="none" />
    </svg>
  </span>
  <img
    v-else-if="kind === 'hat'"
    class="halloween-hat"
    :src="witchHat"
    alt=""
    aria-hidden="true"
    draggable="false"
  />
  <span
    v-else
    class="halloween-lantern"
    :style="{ backgroundImage: 'url(' + JSON.stringify(lantern) + ')' }"
    aria-hidden="true"
  />
</template>

<style scoped>
.halloween-sidebar,
.halloween-title,
.halloween-hat,
.halloween-wordmark,
.halloween-lantern {
  pointer-events: none;
  user-select: none;
}
.halloween-sidebar {
  flex: none;
  padding: 0 12px 5px;
  text-align: center;
  color: #956735;
}
.halloween-sidebar__art {
  position: relative;
  margin: 0 auto;
  max-width: 210px;
  height: 128px;
  background: radial-gradient(ellipse at 50% 68%, #dea45c18, transparent 69%);
}
.halloween-sidebar__art img {
  position: absolute;
  display: block;
  object-fit: contain;
}
.halloween-sidebar__garden {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  color: #687d83;
}
.halloween-sidebar__operator {
  left: 13px;
  bottom: 8px;
  width: 70px;
  height: 116px;
}
.halloween-sidebar__guest {
  right: 2px;
  bottom: 8px;
  width: 103px;
  height: 109px;
}
.halloween-sidebar__pumpkin {
  left: calc(50% - 20px);
  bottom: 3px;
  width: 40px;
  height: 40px;
}
.halloween-sidebar__caption {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 3px;
  line-height: 20px;
}
.halloween-sidebar__rule {
  width: 21px;
  height: 1px;
  background: currentColor;
  opacity: 0.3;
}
.halloween-sidebar__subtitle {
  display: block;
  font-size: 8px;
  letter-spacing: 1.8px;
  line-height: 16px;
  opacity: 0.75;
}
.halloween-title {
  position: relative;
  display: flex;
  flex: none;
  align-items: center;
  gap: 7px;
  height: 28px;
  margin: -3px 0 0 auto;
  padding: 0 45px 0 20px;
  color: #956735;
  white-space: nowrap;
}
.halloween-title > img {
  width: 68px;
  height: 28px;
}
.halloween-title__web {
  position: absolute;
  right: -18px;
  top: -4px;
  width: 56px;
  height: 36px;
  opacity: 0.32;
}
.halloween-hat {
  position: absolute;
  width: 29px;
  height: 24px;
  top: -9px;
  left: -4px;
  transform: rotate(-16deg);
}
.halloween-wordmark {
  position: absolute;
  inset: 0;
}
.halloween-wordmark__hat {
  position: absolute;
  left: -9px;
  top: -12px;
  width: 28px;
  height: 23px;
  background: center / contain no-repeat;
  transform: rotate(-20deg);
}
.halloween-wordmark__bat {
  position: absolute;
  top: -6px;
  right: -20px;
  width: 26px;
  height: 16px;
  transform: rotate(10deg);
}
@media (max-width: 700px) {
  .halloween-wordmark__hat {
    top: -7px;
    left: -7px;
    width: 24px;
    height: 19px;
  }
  .halloween-wordmark__bat {
    top: -3px;
    right: -17px;
    width: 22px;
    height: 13px;
  }
}
.halloween-lantern {
  display: block;
  width: 28px;
  height: 28px;
  object-fit: contain;
  background-size: contain;
  background-position: center;
  background-repeat: no-repeat;
}
:global(html[data-mower-theme='dark'] .halloween-sidebar),
:global(html[data-mower-theme='dark'] .halloween-title) {
  color: #ddb57a;
}
@media (max-width: 1000px) {
  .halloween-title {
    padding-right: 28px;
  }
  .halloween-title > span {
    display: none;
  }
}
@media (max-width: 700px) {
  .halloween-title {
    display: none;
  }
}
@media (max-height: 700px) {
  .halloween-sidebar {
    display: none;
  }
}
</style>
