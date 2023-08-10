import {defineStore} from "pinia";
import axios from "axios";

export const useRecordStore = defineStore('record', () => {
    async function getMoodRatios() {
        const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/record/getMoodRatios`)
        return response.data
    }

    return {
        getMoodRatios
    }
})