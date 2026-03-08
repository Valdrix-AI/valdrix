type ServerLogLevel = 'error' | 'warn' | 'info';

function emitServerLog(level: ServerLogLevel, message: string, context?: unknown): void {
	if (context === undefined) {
		console[level](message);
		return;
	}
	console[level](message, context);
}

export const serverLogger = {
	error(message: string, context?: unknown): void {
		emitServerLog('error', message, context);
	},
	warn(message: string, context?: unknown): void {
		emitServerLog('warn', message, context);
	},
	info(message: string, context?: unknown): void {
		emitServerLog('info', message, context);
	}
};
