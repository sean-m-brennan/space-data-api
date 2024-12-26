/*
  Copyright 2024 Sean M. Brennan and contributors

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/

import {v4 as uuid4} from 'uuid'


export interface vector {
    x: number
    y: number
    z: number
}

const array2vector = (arr: [number, number, number]): vector => {
    return {x: arr[0], y: arr[1], z: arr[2]} as vector
}

export interface SpaceDataConfig {
    host: string | null
    port: number
    secure: boolean
}

interface ServerResponses {
    ident: string
    error: string
    coordinates: [number, number, number]
    position: [number, number, number]
}


export class SpaceData {
    private readonly baseUrl: string
    private readonly debug: boolean
    private cachedToken: string | null
    private expiration: number


    constructor(config: SpaceDataConfig, debug: boolean = false) {
        const proto = config.secure ? 'https' : 'http'
        this.baseUrl = `${proto}://${config.host}:${config.port}`
        this.debug = debug
        this.debug = true
        this.cachedToken = null
        this.expiration = 0
    }

    async check(): Promise<SpaceData | null> {
        try {
            await fetch(`${this.baseUrl}/check`)
            if (this.debug)
                console.debug("Service is available")
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
        } catch (_e) {
            console.warn("Space data service is unavailable")
            return null
        }
        return this
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    noLoading = (_: boolean) => {}

    genericError = (err: unknown) => {
        console.error(err)
    }


    async dataFromServer(ident: string, url: string,
                         setData: ((data: ServerResponses) => void) | null = null,
                         isLoading: (on: boolean) => void = this.noLoading,
                         onError: (err: unknown) => void = this.genericError): Promise<ServerResponses> {
        let error: unknown
        try {
            isLoading(true)
            let latest: Response | null = null
            try {
                const tooClose = Date.now() - 60 * 1000
                if (this.cachedToken === null || this.expiration <= tooClose) {
                    const user = import.meta.env.VITE_OAUTH_USER as string
                    const pwd = import.meta.env.VITE_OAUTH_PWD as string
                    const data = new FormData()
                    data.append('username', user)
                    data.append('password', pwd)
                    latest = await fetch(this.authUrl(), {method: 'POST', body: data})
                    this.cachedToken = await latest.text()  // opaque
                    if (this.debug)
                        console.debug(this.cachedToken)
                    this.expiration = Date.now() + 20 * 60 * 1000  // 20 minutes
                }

                console.log("Fetch")
                // FIXME graceful degrade
                latest = await fetch(url, {method: 'GET', headers: {'Authorization': 'Bearer ' + this.cachedToken}})
                const json = await latest.json() as ServerResponses
                if (json.ident !== ident) {
                    error = `Out-of-order messaging (expected ${ident} got ${json.ident}`
                    console.debug(json)
                    onError(error)
                } else if (json.error) {
                    error = json.error
                    onError(json.error)
                } else {
                    if (setData)
                        setData(json)
                    return json
                }
            } catch (err) {
                error = err
                onError(err)
                console.debug(latest);  // FIXME remove
            }
        } catch (err) {
            console.log("Handle fetch error")
            error = err
            onError(err)
            console.debug(url);  // FIXME remove
        } finally {
            isLoading(false)
        }
        return {error: error} as ServerResponses
    }

    conversionUrl(ident: string, coords: vector, datetime: Date) {
        return `${this.baseUrl}/convert/?ident=${ident}&coords=[${coords.x},${coords.y},${coords.z}]&dt_str=${datetime.toISOString()}`
    }

    llaToJ2000Url(ident: string, lat: number, lon: number, alt: number, datetime: Date) {
        return `${this.baseUrl}/fixed2j2k/?ident=${ident}&lat=${lat}&lon=${lon}&alt=${alt}&dt_str=${datetime.toISOString()}`
    }

    currentPositionUrl(ident: string, objName: string, datetime: Date) {
        return `${this.baseUrl}/position/?ident=${ident}&body=${objName}&dt_str=${datetime.toISOString()}`
    }

    authUrl() {
        return `${this.baseUrl}/token`
    }

    async fixedToJ2000(datetime: Date, lat: number, lon: number, alt: number,
                       onError: (err: unknown) => void = this.genericError): Promise<vector> {
        const ident = uuid4()
        const url =  this.llaToJ2000Url(ident, lat, lon, alt, datetime)
        const data = await this.dataFromServer(ident, url, null, this.noLoading, onError)
        if (data.error)
            throw new Error(data.error)
        return array2vector(data.coordinates)
    }

    async currentPosition(datetime: Date, objName: string,
                          onError: (err: unknown) => void = this.genericError): Promise<vector> {
        const ident = uuid4()
        const url = this.currentPositionUrl(ident, objName, datetime)
        const data = await this.dataFromServer(ident, url, null, this.noLoading, onError)
        if (data.error)
            throw new Error(data.error)
        return array2vector(data.position)
    }
}