import { readFileSync } from 'node:fs'
import { baseParse } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { NUpload } from 'naive-ui'
import { createSSRApp, defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CONFIG_GENERATION_HEADER } from '@/composables/configProfiles'

const uploads = [
  ['normal plan', '../pages/Plan.vue', 'import_url', false, '/api/import', 'img'],
  ['rescue plan', '../pages/Plan.vue', 'import_url', true, '/api/import?rescue=1', 'img']
]

function uploadProps(path, actionName, rescue, axios) {
  const { descriptor } = parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'native-upload-request-test' })
  const initializer = script.scriptSetupAst
    .flatMap((node) => node.declarations || [])
    .find((node) => node.id.name === actionName).init
  const source = descriptor.scriptSetup.content
    .slice(initializer.start, initializer.end)
    .replaceAll('import.meta.env.VITE_HTTP_URL', JSON.stringify('/api'))
  const action = new Function('rescue', `return (${source})`)(rescue)
  function find(node) {
    if (node.tag === 'n-upload') return node
    return node.children?.map(find).find(Boolean)
  }
  const upload = find(baseParse(descriptor.template.content))
  const headers = upload.props.find(
    (prop) => prop.name === 'bind' && prop.arg?.content === 'headers'
  ).exp.content
  const actualAction = upload.props.find(
    (prop) => prop.name === 'bind' && prop.arg?.content === 'action'
  ).exp.content
  expect(actualAction).toBe(actionName)
  return {
    action,
    name: upload.props.find((prop) => prop.name === 'name').value.content,
    headers: new Function('token', 'axios', 'CONFIG_GENERATION_HEADER', `return (${headers})`)(
      'page-token',
      axios,
      CONFIG_GENERATION_HEADER
    )
  }
}

async function uploader(props) {
  let instance
  const Harness = defineComponent({
    ...NUpload,
    setup(props) {
      instance = NUpload.setup(props)
      return instance
    },
    render: () => null
  })
  await renderToString(
    createSSRApp(Harness, {
      ...props,
      defaultFileList: [
        { id: 'selected-file', name: 'upload.json', status: 'pending', file: new Blob(['{}']) }
      ]
    })
  )
  return instance
}

afterEach(() => vi.unstubAllGlobals())

describe('native configuration uploads', () => {
  it.each(uploads)(
    '%s sends the page generation when its native request starts',
    async (_label, path, actionName, rescue, expectedAction, expectedField) => {
      const requests = []
      class Request {
        headers = {}
        upload = {}
        open(method, url) {
          this.method = method
          this.url = url
        }
        setRequestHeader(name, value) {
          this.headers[name] = value
        }
        send(body) {
          this.body = body
          requests.push(this)
        }
      }
      vi.stubGlobal('XMLHttpRequest', Request)
      const axios = { defaults: { headers: { common: {} } } }
      const mountedBeforeBootstrap = await uploader(uploadProps(path, actionName, rescue, axios))
      axios.defaults.headers.common[CONFIG_GENERATION_HEADER] = 'activated-page-generation'
      mountedBeforeBootstrap.submit()

      expect(requests[0].method).toBe('POST')
      expect(requests[0].url).toBe(expectedAction)
      expect(requests[0].body.get(expectedField)).toBeInstanceOf(Blob)
      expect(requests[0].headers).toEqual({
        token: 'page-token',
        [CONFIG_GENERATION_HEADER]: 'activated-page-generation'
      })

      const mountedAfterReload = await uploader(uploadProps(path, actionName, rescue, axios))
      mountedAfterReload.submit()
      expect(requests[1].headers).toEqual(requests[0].headers)
      expect(axios.defaults.headers.common[CONFIG_GENERATION_HEADER]).toBe(
        'activated-page-generation'
      )
    }
  )
})
