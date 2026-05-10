package simfront

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.context.properties.ConfigurationPropertiesScan
import org.springframework.boot.runApplication

@SpringBootApplication
@ConfigurationPropertiesScan
class SimbackApplication

fun main(args: Array<String>) {
	runApplication<SimbackApplication>(*args)
}
