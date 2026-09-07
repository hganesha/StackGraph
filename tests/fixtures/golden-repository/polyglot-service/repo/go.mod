module github.com/acme/billing

go 1.22

require (
	github.com/gin-gonic/gin v1.9.1
	github.com/acme/shared v0.4.0
)

replace github.com/acme/shared => ../shared
