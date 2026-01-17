/**
 * API Client - REST API wrapper with error handling
 * Provides a consistent interface for making API calls
 */
class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl || window.location.origin;
        this.defaultHeaders = {
            'Content-Type': 'application/json'
        };
    }

    /**
     * Make an HTTP request
     * @param {string} method - HTTP method
     * @param {string} endpoint - API endpoint
     * @param {Object} [options] - Request options
     * @returns {Promise<any>}
     */
    async request(method, endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            method,
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };

        if (options.body && typeof options.body === 'object') {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new ApiError(
                    errorData.detail || errorData.message || `Request failed with status ${response.status}`,
                    response.status,
                    errorData
                );
            }

            // Handle empty responses
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            return await response.text();
        } catch (error) {
            if (error instanceof ApiError) {
                throw error;
            }
            throw new ApiError(
                error.message || 'Network error',
                0,
                { originalError: error }
            );
        }
    }

    /**
     * GET request
     * @param {string} endpoint
     * @param {Object} [params] - Query parameters
     * @returns {Promise<any>}
     */
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return this.request('GET', url);
    }

    /**
     * POST request
     * @param {string} endpoint
     * @param {Object} [body] - Request body
     * @returns {Promise<any>}
     */
    async post(endpoint, body = {}) {
        return this.request('POST', endpoint, { body });
    }

    /**
     * PUT request
     * @param {string} endpoint
     * @param {Object} [body] - Request body
     * @returns {Promise<any>}
     */
    async put(endpoint, body = {}) {
        return this.request('PUT', endpoint, { body });
    }

    /**
     * PATCH request
     * @param {string} endpoint
     * @param {Object} [body] - Request body
     * @returns {Promise<any>}
     */
    async patch(endpoint, body = {}) {
        return this.request('PATCH', endpoint, { body });
    }

    /**
     * DELETE request
     * @param {string} endpoint
     * @returns {Promise<any>}
     */
    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }
}

/**
 * Custom API Error class
 */
class ApiError extends Error {
    constructor(message, status, data = {}) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }

    /**
     * Check if error is a network error
     */
    isNetworkError() {
        return this.status === 0;
    }

    /**
     * Check if error is a client error (4xx)
     */
    isClientError() {
        return this.status >= 400 && this.status < 500;
    }

    /**
     * Check if error is a server error (5xx)
     */
    isServerError() {
        return this.status >= 500;
    }
}

// Export singleton and class
export const apiClient = new ApiClient();
export { ApiClient, ApiError };
export default ApiClient;
