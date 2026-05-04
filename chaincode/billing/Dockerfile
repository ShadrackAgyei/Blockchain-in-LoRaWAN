FROM golang:1.21-alpine AS builder
WORKDIR /chaincode
COPY go.mod go.sum ./
COPY vendor/ vendor/
COPY billing.go .
RUN CGO_ENABLED=0 go build -mod=vendor -o chaincode .

FROM alpine:3.18
COPY --from=builder /chaincode/chaincode /chaincode
EXPOSE 9999
CMD ["/chaincode"]
