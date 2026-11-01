/** Native Python exception categories used by the pinned infra_main/BaseSolver.run boundaries. */
export class MowerExitError extends Error {}
export class MowerRecognizeError extends Error {override name='RecognizeError'}
export class MowerConnectionError extends Error {}
export class MowerConnectionAbortedError extends Error {}
export class MowerAttributeError extends Error {}
/** Native infra_main catches this recoverable preview failure and retains the task. */
export class MowerShiftPreviewError extends Error {override name='MowerShiftPreviewError'}
/** Native alpha keeps the current task and retries its remaining rooms later. */
export class MowerRoomArrangementDeferred extends Error {
 override name='RoomArrangementDeferred'
 constructor(readonly room:string,readonly cause:unknown){super(cause instanceof Error?cause.message:String(cause))}
}
export function rethrowMowerInfraFatal(error:unknown):void {
 if(error instanceof MowerExitError||
  error instanceof Error&&[MowerConnectionError,MowerConnectionAbortedError,MowerAttributeError].some(type=>error.constructor===type))throw error
}
