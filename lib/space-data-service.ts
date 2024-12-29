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

import {
    AuthToken,
    Body__token_post,
    CartesianCoords,
    celestial2TerrestrialPost,
    checkGet,
    client,
    ConversionResp,
    convertPost,
    CoordRefFrame,
    HTTPValidationError,
    positionPost,
    PositionResp,
    SphericalCoords,
    terrestrial2CelestialPost,
    tokenPost
} from './client'  // generated by `npm run generate-client` (while server is running)

export type {CartesianCoords, SphericalCoords} from './client'
export type SphericalTag = "spherical"
export type CartesianTag = "cartesian"


interface Message {
    ident?: string
    error?: string
}

interface ServerResponse {
    data?: unknown
    error?:  HTTPValidationError
}

export interface SpaceDataConfig {
    host: string | null
    port: number
    secure: boolean
}

export default class SpaceData {
    private readonly baseUrl: string
    private readonly debug: boolean
    private cachedToken: AuthToken | null
    private expiration: number


    constructor(config: SpaceDataConfig, debug: boolean = false) {
        const proto = config.secure ? 'https' : 'http'
        this.baseUrl = `${proto}://${config.host}:${config.port}`
        this.debug = debug
        this.cachedToken = null
        this.expiration = 0

        client.setConfig({
            baseUrl: this.baseUrl,
        })
    }

    async check(): Promise<SpaceData | null> {
        try {
            await checkGet()
            if (this.debug)
                console.debug("Service is available")
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
        } catch (_e) {
            console.warn("Space data service is unavailable")
            return null
        }
        return this
    }

    validateResponse(resp: ServerResponse, ident?: string) {
        if (resp.error && resp.error.detail && resp.error.detail.length > 0) {
            let msg = ""
            resp.error.detail.forEach(detail => {
                msg += detail.msg + "\n"
            })
            throw new Error(`Validation error: ${msg}`)
        }
        const data = resp.data! as Message
        if (data.error)
            throw new Error(data.error)
        if (ident && data.ident != ident)
            throw new Error(`Out-of-order messaging (expected ${ident} got ${data.ident}`)
    }

    async tryLogin() {
        const tooClose = Date.now() - 60 * 1000
        if (this.cachedToken === null || this.expiration <= tooClose) {
            const user = import.meta.env.VITE_OAUTH_USER as string
            const pwd = import.meta.env.VITE_OAUTH_PWD as string
            const data = {username: user, password: pwd} as Body__token_post
            const resp = await tokenPost({body: data})//fetch(this.authUrl(), {method: 'POST', body: data})
            this.validateResponse(resp)
            this.cachedToken = resp.data!  // opaque
            if (this.debug)
                console.debug(this.cachedToken)
            this.expiration = Date.now() + 20 * 60 * 1000  // 20 minutes
        }
        client.interceptors.request.use((request) => {
            request.headers.set('Authorization', `Bearer ${JSON.stringify(this.cachedToken)}`)
            return request;
        });
    }

    async convertCoords(datetime: Date, coords: CartesianCoords | SphericalCoords,
                        origFrame: CoordRefFrame, newFrame: CoordRefFrame): Promise<CartesianCoords|SphericalCoords> {
        await this.tryLogin()
        const ident = uuid4()
        const dataIn = {ident: ident, coords: coords, original: origFrame, new: newFrame, dt: datetime.toISOString()}
        const resp = await convertPost({body: dataIn})
        this.validateResponse(resp, ident)
        return (resp.data as ConversionResp).coordinates
    }

    async fixedToJ2000(datetime: Date, lat: number, lon: number, alt: number,
                       units: string = 'km'): Promise<CartesianCoords> {
        await this.tryLogin()
        const ident = uuid4()
        const coordsIn = {coord_type: "spherical" as SphericalTag, lat: lat, lon: lon, alt: alt, units: units}
        const dataIn = {ident: ident, coords: coordsIn, dt: datetime.toISOString()}
        console.log(dataIn)  // FIXME
        const resp = await terrestrial2CelestialPost({body: dataIn})
        this.validateResponse(resp, ident)
        return (resp.data as ConversionResp).coordinates as CartesianCoords
    }

    async J2000ToFixed(datetime: Date, x: number, y: number, z: number,
                       units: string = 'km'): Promise<SphericalCoords> {
        await this.tryLogin()
        const ident = uuid4()
        const coordsIn = {coord_type: "cartesian" as CartesianTag, x: x, y: y, z: z, units: units}
        const dataIn = {ident: ident, coords: coordsIn, dt: datetime.toISOString()}
        const resp = await celestial2TerrestrialPost({body: dataIn})
        this.validateResponse(resp, ident)
        return (resp.data as ConversionResp).coordinates as SphericalCoords
    }

    async currentPosition(datetime: Date, objName: string): Promise<CartesianCoords> {
        await this.tryLogin()
        const ident = uuid4()
        const paramsIn = {ident: ident, body: objName, dt: datetime.toISOString()}
        const resp = await positionPost({body: paramsIn})
        this.validateResponse(resp, ident)
        return (resp.data as PositionResp).position
    }
}