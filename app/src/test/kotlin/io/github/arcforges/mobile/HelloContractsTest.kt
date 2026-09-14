// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import io.github.arcforges.contracts.hello.v1.HelloServiceGrpcKt
import io.github.arcforges.contracts.hello.v1.SayHelloRequest
import io.github.arcforges.contracts.hello.v1.SayHelloResponse
import io.grpc.Status
import io.grpc.StatusException
import io.grpc.inprocess.InProcessChannelBuilder
import io.grpc.inprocess.InProcessServerBuilder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class HelloContractsTest {
    @Test
    fun publishedContractPreservesUnicode() {
        assertEquals("Hello,  世界 👋 !", localContractGreeting(" 世界 👋 "))
    }

    @Test
    fun publishedCoroutineClientCallsServiceAndPreservesStatus() = runBlocking {
        val address = InProcessServerBuilder.generateName()
        val service =
            object : HelloServiceGrpcKt.HelloServiceCoroutineImplBase() {
                override suspend fun sayHello(request: SayHelloRequest): SayHelloResponse {
                    if (request.name.isEmpty()) throw Status.INVALID_ARGUMENT.asException()
                    return SayHelloResponse.newBuilder()
                        .setMessage("Hello, ${request.name}!")
                        .build()
                }
            }
        val server =
            InProcessServerBuilder.forName(address)
                .directExecutor()
                .addService(service)
                .build()
                .start()
        val channel = InProcessChannelBuilder.forName(address).directExecutor().build()
        try {
            val client = HelloClient(channel)
            assertEquals("Hello, World!", client.sayHello("World"))
            val error =
                assertThrows(StatusException::class.java) { runBlocking { client.sayHello("") } }
            assertEquals(Status.Code.INVALID_ARGUMENT, error.status.code)
        } finally {
            channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS)
            server.shutdownNow().awaitTermination(5, TimeUnit.SECONDS)
        }
    }
}
