import axios from 'axios'

export async function file_dialog() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/file`)
  return response.data
}

export async function folder_dialog() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/folder`)
  return response.data
}
